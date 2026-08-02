"""BrowserEnv: play a live quordle.com Practice game via Playwright (ADR 13)."""

from types import TracebackType

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from quordle.browser import scraper
from quordle.engine import TurnResult

QUORDLE_URL = "https://beta.quordle.com"
REVEAL_TIMEOUT_MS = 8000


class GuessRejected(Exception):
    """The site rejected a guess (not in its word list); the row did not advance."""


class BrowserEnv:
    def __init__(
        self,
        *,
        allowed: frozenset[str],
        headless: bool = True,
        max_guesses: int = 9,
        num_boards: int = 4,
    ) -> None:
        self.allowed = allowed
        self.max_guesses = max_guesses
        self.num_boards = num_boards
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._page: Page = self._browser.new_page()
        self._page.goto(QUORDLE_URL)
        self._page.get_by_text("Practice", exact=True).click()
        self._page.wait_for_selector('[aria-label="Game Board 1"] .quordle-box')

    def _read_boards(self) -> list[list[list[str]]]:
        boards: list[list[list[str]]] = []
        for n in range(1, self.num_boards + 1):
            labels = self._page.eval_on_selector_all(
                f'[aria-label="Game Board {n}"] .quordle-box',
                "els => els.map(e => e.getAttribute('aria-label'))",
            )
            rows = [labels[i : i + 5] for i in range(0, len(labels), 5)]
            boards.append(rows)
        return boards

    def _type_word(self, word: str) -> None:
        for ch in word.upper():
            # `:has-text("{ch}")` (as originally drafted) is a case-insensitive
            # substring match, and ambiguously also matches the Backspace and
            # Enter keys (their aria-labels/text are "Backspace Key" / "Enter
            # Key", which contain most letters, e.g. "C" is in "ba-C-kspa-C-e").
            # Live validation (RUN_BROWSER_TESTS=1) showed this actually
            # clicked Backspace instead of "C" mid-word, silently corrupting
            # the guess. Match the letter key's aria-label prefix instead
            # (e.g. "'C' key. Not guessed.") for an unambiguous, single match.
            self._page.click(f".quordle-key[aria-label^=\"'{ch}' key\"]")
        # The Enter key renders as an SVG icon, not the "↵" glyph the brief
        # assumed; live validation showed the on-screen key has no matching
        # text, only aria-label="Enter Key" (confirmed via DOM inspection:
        # <button class="quordle-key" aria-label="Enter Key"> containing an
        # <svg><title>Enter Key</title>...). Match on that instead, scoped to
        # .quordle-key so it can't hit an unrelated element.
        self._page.click('.quordle-key[aria-label="Enter Key"]')

    def remaining_guesses(self) -> int:
        return self.max_guesses - scraper.count_played(self._read_boards())

    def finished(self) -> bool:
        boards = self._read_boards()
        used = scraper.count_played(boards)
        if used >= self.max_guesses:
            return True
        return all(scraper.solved_on(board) is not None for board in boards)

    def read_answers(self) -> list[str]:
        """The four board answers the site reveals at game-over (uppercase, in
        board order), or [] if the game is not over (no results modal).

        Answer-blind (ADR 13): only read after a game ends -- never consulted
        during play.
        """
        try:
            self._page.wait_for_selector(
                '[aria-label="Link to word definition"]', timeout=REVEAL_TIMEOUT_MS
            )
        except PlaywrightTimeoutError:
            return []
        texts = self._page.eval_on_selector_all(
            '[aria-label="Link to word definition"]',
            "els => els.map(e => (e.innerText || '').trim().toUpperCase())",
        )
        return [t for t in texts if t]

    def new_game(self) -> None:
        """Start a fresh practice game in the current page.

        Fast path: click the results modal's "New Practice Game" button when
        the game reached game-over (match the button's aria-label, not its
        text -- get_by_text resolves to the SVG <title>, same gotcha as the
        Enter key).

        Fallback (issue #22): when we ended a game early ourselves (a stall or
        rejection), there is no results modal, so the button is absent. The
        practice game persists in localStorage -- a plain reload or Practice
        re-click RESUMES the partial game rather than resetting it (scouted
        2026-08-02) -- so clear storage first, then reload and re-enter
        Practice to force a fresh puzzle. This lets a multi-game batch continue
        past an early-ended game instead of stopping.
        """
        button = self._page.locator('button[aria-label="New Practice Game"]')
        if button.count() > 0:
            button.first.click()
        else:
            self._page.evaluate("() => localStorage.clear()")
            self._page.goto(QUORDLE_URL)
            self._page.get_by_text("Practice", exact=True).click()
            self._page.wait_for_selector('[aria-label="Game Board 1"] .quordle-box')
        self._page.wait_for_function(
            """
            (numBoards) => {
                const isPlayed = (label) =>
                    !!label && (
                        label.includes('is correct') ||
                        label.includes('is in a different spot') ||
                        label.includes('is incorrect')
                    );
                for (let b = 1; b <= numBoards; b++) {
                    const boxes = document.querySelectorAll(
                        `[aria-label="Game Board ${b}"] .quordle-box`
                    );
                    for (const e of boxes) {
                        if (isPlayed(e.getAttribute('aria-label'))) return false;
                    }
                }
                return true;
            }
            """,
            arg=self.num_boards,
            timeout=REVEAL_TIMEOUT_MS,
        )

    def submit(self, guess: str) -> TurnResult:
        guess = guess.upper()
        if len(guess) != 5 or guess not in self.allowed:
            raise ValueError(f"invalid guess: {guess!r}")
        if self.finished():
            raise RuntimeError("game already finished")
        before = scraper.count_played(self._read_boards())
        self._type_word(guess)
        # Wait until the MAX played-row count across ALL boards reaches
        # before+1 -- i.e. scraper.count_played(all boards) >= before+1.
        #
        # An earlier version only watched Game Board 1's target row. That
        # broke as soon as board 1 was solved: solved boards freeze (stop
        # getting new rows -- that's exactly why count_played() takes the
        # MAX across boards, not board 1's count), so every later accepted
        # guess targeted a board-1 row that would never play, timing out
        # into a spurious GuessRejected and aborting the game mid-play. It
        # also risked reading board 2-4 while they still lagged board 1,
        # producing a parse_row ValueError on an unplayed row.
        #
        # Watching all boards' max fixes both: a rejected guess advances no
        # board, so the max stays at `before` and we still time out
        # correctly into GuessRejected; an accepted guess advances every
        # still-active board, so the max reaches before+1 as soon as they've
        # all revealed. "Played" is defined the same way scraper.tile_mark
        # does (correct / different spot / incorrect), not by negating the
        # (growing) list of "unplayed" reasons, so this doesn't bit-rot the
        # way the board-1-only version did when a new unplayed label turned
        # up ("is a future guess", then "never guessable" once solved).
        wait_js = """
            ({ before, numBoards }) => {
                const isPlayed = (label) =>
                    !!label && (
                        label.includes('is correct') ||
                        label.includes('is in a different spot') ||
                        label.includes('is incorrect')
                    );
                let maxPlayed = 0;
                for (let b = 1; b <= numBoards; b++) {
                    const boxes = document.querySelectorAll(
                        `[aria-label="Game Board ${b}"] .quordle-box`
                    );
                    let played = 0;
                    for (let r = 0; r * 5 < boxes.length; r++) {
                        const row = [...boxes].slice(r * 5, r * 5 + 5);
                        const rowPlayed = row.length === 5 && row.every(
                            (e) => isPlayed(e.getAttribute('aria-label'))
                        );
                        if (rowPlayed) {
                            played++;
                        }
                    }
                    maxPlayed = Math.max(maxPlayed, played);
                }
                return maxPlayed >= before + 1;
            }
        """
        try:
            self._page.wait_for_function(
                wait_js,
                arg={"before": before, "numBoards": self.num_boards},
                timeout=REVEAL_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError as exc:  # no board advanced -> rejected word
            raise GuessRejected(f"guess not accepted by the site: {guess!r}") from exc
        boards = self._read_boards()
        used = scraper.count_played(boards)
        return TurnResult(used, scraper.read_turn(boards, used))

    def close(self) -> None:
        self._browser.close()
        self._pw.stop()

    def __enter__(self) -> "BrowserEnv":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
