# A minimal Ren'Py project for inspector smoke tests (not a shipped game).
default player_stats = {"hp": 10, "items": ["key"]}

default persistent.inspector_test_flag = False

# Named-store fixture for v0.3 search and discovery.
default characters.affection = {"alice": 7}

label start:
    "Press F8 to open the inspector. Try Find: hp and the Overview/Scripts tabs."
    "Use Named to inspect characters.affection and pin the alice entry."
    $ player_stats["hp"] = 8
    "The pinned health value should change to 8."
    $ player_stats["items"].append("map")
    "Inventory now contains key and map. Save, load and roll back to inspect refresh."
    $ player_stats = {"hp": 42, "items": ["new"]}
    "After replacement, the pinned health value should change to 42."
    return
