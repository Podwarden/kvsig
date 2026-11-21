import json

import pytest

from kvsig import jsontext
from kvsig.jsontext import dump, es6_number


@pytest.mark.parametrize(
    ("f", "text"),
    [
        # RFC 8785 Appendix B and ECMAScript Number.prototype.toString
        (0.0, "0"),
        (-0.0, "0"),
        (1.0, "1"),
        (-1.5, "-1.5"),
        (100.0, "100"),
        (4.35, "4.35"),
        (0.002, "0.002"),
        (1e-6, "0.000001"),
        (1e-7, "1e-7"),
        (1e21, "1e+21"),
        (1e20, "100000000000000000000"),
        (123456789012345680000.0, "123456789012345680000"),
        (333333333.3333333, "333333333.3333333"),
        (5e-324, "5e-324"),
        (1.7976931348623157e308, "1.7976931348623157e+308"),
        (9007199254740992.0, "9007199254740992"),
        (295147905179352830000.0, "295147905179352830000"),
        (1.2345e-10, "1.2345e-10"),
        (float("nan"), "null"),
        (float("inf"), "null"),
    ],
)
def test_es6_number(f, text):
    assert es6_number(f) == text


def test_integers():
    assert dump(2**53) == "9007199254740992"
    assert dump(-(2**53)) == "-9007199254740992"
    # beyond 2^53: rounded to a double, then printed as ECMAScript would
    assert dump(2**53 + 1) == "9007199254740992"
    # too large for a double: full decimal
    assert dump(10**400) == "1" + "0" * 400


def test_member_order_kept_or_sorted():
    v = {"b": 1, "a": [True, None, "x"]}
    assert dump(v) == '{"b":1,"a":[true,null,"x"]}'
    assert dump(v, sort=True) == '{"a":[true,null,"x"],"b":1}'


def test_sort_is_by_code_point():
    # UTF-16 order would put U+FF61 after U+1F600's high surrogate; code-point order does not
    v = {"\U0001f600": 1, "\uff61": 2}
    assert dump(v, sort=True) == '{"\uff61":2,"\U0001f600":1}'


def test_string_escapes():
    s = '"\\\b\f\n\r\t\x00\x1f\x7f\u2028é/'
    assert dump(s) == '"\\"\\\\\\b\\f\\n\\r\\t\\u0000\\u001f\x7f\u2028é/"'
    assert json.loads(dump(s)) == s


def test_lone_surrogate_in_string_and_key():
    assert dump({"\ud800": "x\udfff"}) == '{"\ufffd":"x\ufffd"}'


def test_too_deep():
    v: list = []
    cur = v
    for _ in range(jsontext.MAX_DEPTH):
        cur.append([])
        cur = cur[0]
    with pytest.raises(jsontext.TooDeep):
        dump(v)


def test_round_trip_is_a_fixed_point():
    v = json.loads('{"z":1e2,"a":[0.1,-0,1E21,"\\u00e9"],"m":{"y":null}}')
    once = dump(v)
    assert dump(json.loads(once)) == once
    assert once == '{"z":100,"a":[0.1,0,1e+21,"é"],"m":{"y":null}}'
