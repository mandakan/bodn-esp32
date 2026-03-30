# bodn/stories/__init__.py — built-in flash story (fallback when no SD card)
#
# A tiny 5-node story that works without an SD card.  Serves as proof-of-
# concept and ensures Story Mode is always functional even on a bare device.

BUILTIN_STORY = {
    "id": "forest_walk",
    "version": 1,
    "title": {"sv": "Skogspromenaden", "en": "The Forest Walk"},
    "author": "Bodn",
    "age_min": 3,
    "age_max": 5,
    "estimated_minutes": 1,
    "narrate_choices": True,
    "start": "start",
    "nodes": {
        "start": {
            "text": {
                "sv": "Du och din nallebjörn går på en stig i skogen. Solen skiner mellan löven.",
                "en": "You and your teddy bear walk along a forest path. The sun shines through the leaves.",
            },
            "mood": "warm",
            "choices": [
                {
                    "label": {"sv": "Följa stigen", "en": "Follow the path"},
                    "next": "clearing",
                },
                {
                    "label": {"sv": "Titta på blommorna", "en": "Look at the flowers"},
                    "next": "flowers",
                },
            ],
        },
        "clearing": {
            "text": {
                "sv": "Stigen leder till en liten glänta. Där sitter en ekorre och äter en nöt!",
                "en": "The path leads to a little clearing. A squirrel is sitting there eating a nut!",
            },
            "mood": "wonder",
            "choices": [
                {
                    "label": {"sv": "Vinka till ekorren", "en": "Wave to the squirrel"},
                    "next": "squirrel_end",
                },
                {
                    "label": {"sv": "Gå vidare", "en": "Keep walking"},
                    "next": "home_end",
                },
            ],
        },
        "flowers": {
            "text": {
                "sv": "Du hittar vackra blå blommor! Nallen tycker de luktar gott.",
                "en": "You find beautiful blue flowers! Teddy thinks they smell lovely.",
            },
            "mood": "happy",
            "choices": [
                {
                    "label": {"sv": "Plocka en blomma", "en": "Pick a flower"},
                    "next": "home_end",
                },
            ],
        },
        "squirrel_end": {
            "text": {
                "sv": "Ekorren vinkar tillbaka med svansen! Sedan hoppar den upp i ett träd. En fin dag i skogen!",
                "en": "The squirrel waves back with its tail! Then it hops up a tree. What a lovely day in the forest!",
            },
            "mood": "happy",
            "ending": True,
            "ending_type": "happy",
        },
        "home_end": {
            "text": {
                "sv": "Du och nallen går hem igen. Det var en fin promenad!",
                "en": "You and teddy walk back home. It was a lovely walk!",
            },
            "mood": "warm",
            "ending": True,
            "ending_type": "gentle",
        },
    },
}
