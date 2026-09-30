from app.utils import sanitise_name, valid_room_code, room_code

def test_sanitise_name():
    assert sanitise_name("<Ash!>") == "Ash"

def test_room_code_format():
    assert valid_room_code(room_code())

def test_invalid_room_code():
    assert not valid_room_code("bad code")
