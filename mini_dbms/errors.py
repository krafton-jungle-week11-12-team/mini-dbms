"""단계별 에러. CLI는 DbError 하나로 모두 잡아요."""


class DbError(Exception):
    pass


class TokenizeError(DbError):
    pass


class ParseError(DbError):
    pass


class ValidationError(DbError):
    pass


class TableNotFoundError(ValidationError):
    """없는 테이블. 서버는 404로 구분하고, CLI는 ValidationError(DbError)로 잡아요."""


def josa(word: str, with_batchim: str, without_batchim: str) -> str:
    """word 뒤에 붙일 조사를 골라요. 예: josa("FROM", "이", "가") → "이"."""
    return with_batchim if _has_batchim(word) else without_batchim


_DIGIT_BATCHIM = set("013678")  # 영 일 삼 육 칠 팔


def _has_batchim(word: str) -> bool:
    w = word.strip("'\"")
    if not w:
        return False
    last = w[-1]
    if "가" <= last <= "힣":
        return (ord(last) - ord("가")) % 28 != 0
    if last.isdigit():
        return last in _DIGIT_BATCHIM
    lower = w.lower()
    if lower[-1] in "lmnkpt":
        return True
    # name, line처럼 끝의 e가 소리 나지 않는 경우
    return len(lower) >= 2 and lower[-1] == "e" and lower[-2] in "lmn"
