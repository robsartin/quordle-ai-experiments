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
        return all(scraper._solved_on(board) is not None for board in boards)

    def submit(self, guess: str) -> TurnResult:
        guess = guess.upper()
        if len(guess) != 5 or guess not in self.allowed:
            raise ValueError(f"invalid guess: {guess!r}")
        before = scraper.count_played(self._read_boards())
        self._type_word(guess)
        # Wait until board 1's SPECIFIC target row (0-based index `before`,
        # the row about to be played) leaves the unplayed state, i.e. all 5
        # of its tiles are neither "being guessed" nor "is a future guess"
        # (so they're correct / different spot / incorrect). This proves the
        # site accepted the word and that exact row advanced.
        #
        # An earlier version checked "any row not still being guessed" across
        # the whole board, which is wrong: with 45 tiles/board and exactly
        # one "being guessed" row at a time, the other 40 tiles are either
        # already-revealed earlier rows or "is a future guess" rows -- the
        # count of non-"being guessed" tiles is constant regardless of
        # whether the new guess was accepted, so the wait resolved instantly
        # every time and a truly-rejected guess never timed out (GuessRejected
        # was unreachable). Keying off the specific target row's own state
        # fixes both: it only flips once genuinely revealed, and stays
        # unplayed forever if the site rejects the guess, so a rejection now
        # correctly times out into GuessRejected. Written as a block function
        # (rather than one long expression) to stay within the project's
        # line-length limit.
        wait_js = """
            (n) => {
                const boxes = document.querySelectorAll(
                    '[aria-label="Game Board 1"] .quordle-box'
                );
                const row = [...boxes].slice(n * 5, n * 5 + 5);
                if (row.length < 5) return false;
                return row.every((e) => {
                    const label = e.getAttribute('aria-label') || '';
                    return !label.includes('being guessed') && !label.includes('future guess');
                });
            }
        """
        try:
            self._page.wait_for_function(
                wait_js,
                arg=before,
                timeout=REVEAL_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError as exc:  # row never advanced -> rejected word
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
