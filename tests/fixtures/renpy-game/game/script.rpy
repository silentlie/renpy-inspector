# A minimal Ren'Py project for inspector smoke tests (not a shipped game).
default player_stats = {"hp": 10, "items": ["key"]}

default persistent.inspector_test_flag = False

label start:
    "Press F8 to open the inspector. Pin player_stats['hp']."
    $ player_stats["hp"] = 8
    "The pinned health value should change to 8."
    $ player_stats["items"].append("map")
    "Inventory now contains key and map. Save, load and roll back to inspect refresh."
    $ player_stats = {"hp": 42, "items": ["new"]}
    "After replacement, the pinned health value should change to 42."
    return
