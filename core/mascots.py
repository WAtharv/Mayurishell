# All mascot designs in this file are original ASCII / Unicode art created for MayuriShell.
# They are not copies or imitations of any existing character, brand, logo, or trademark.
"""Original mascot character designs and reactive expressions for MayuriShell."""
from __future__ import annotations

import random
from typing import NamedTuple

VALID_MASCOTS = ("cat", "bunny", "bear", "fox", "penguin", "shiba")


class MascotArt(NamedTuple):
    name: str
    mood: str
    art_lines: list[str]
    face: str


# --- Unicode / Rich Mascots (Max 12 lines x 24 columns) ---

MASCOTS_UNICODE: dict[str, dict[str, MascotArt]] = {
    "cat": {
        "neutral": MascotArt(
            name="cat",
            mood="neutral",
            art_lines=[
                r"   /\_/\  ",
                r"  ( o.o ) ",
                r"   > ^ <  ",
                r"  /     \ ",
                r" (  . .  )",
                r"  \_-^-/  ",
            ],
            face="(=^･ω･^=)",
        ),
        "happy": MascotArt(
            name="cat",
            mood="happy",
            art_lines=[
                r"   /\_/\  ",
                r"  ( ^.^ )*",
                r"   > ^ <  ",
                r"  /     \ ",
                r" (  . .  )",
                r"  \_-^-/  ",
            ],
            face="(=^･ω･^=) ✨",
        ),
        "worried": MascotArt(
            name="cat",
            mood="worried",
            art_lines=[
                r"   /\_/\  ",
                r"  ( ;.; ) ",
                r"   > ^ <  ",
                r"  /     \ ",
                r" (  . .  )",
                r"  \_-^-/  ",
            ],
            face="(=;･ω･;=) 💦",
        ),
        "sleepy": MascotArt(
            name="cat",
            mood="sleepy",
            art_lines=[
                r"   /\_/\  ",
                r"  ( -.- )z",
                r"   > ^ <  ",
                r"  /     \ ",
                r" (  . .  )",
                r"  \_-^-/  ",
            ],
            face="(=uωu=) zZz",
        ),
    },
    "bunny": {
        "neutral": MascotArt(
            name="bunny",
            mood="neutral",
            art_lines=[
                r"  (\_/)   ",
                r"  ( •.•)  ",
                r"  / >🍪   ",
                r" (  . . ) ",
                r"  o_(\_)  ",
            ],
            face="(\\_/) (•.•)",
        ),
        "happy": MascotArt(
            name="bunny",
            mood="happy",
            art_lines=[
                r"  (\_/)   ",
                r"  ( ^.^)🌸",
                r"  / >💖   ",
                r" (  . . ) ",
                r"  o_(\_)  ",
            ],
            face="(\\_/) (^-^) ✨",
        ),
        "worried": MascotArt(
            name="bunny",
            mood="worried",
            art_lines=[
                r"  (\_/)   ",
                r"  ( >.<)💦",
                r"  / >💔   ",
                r" (  . . ) ",
                r"  o_(\_)  ",
            ],
            face="(\\_/) (>.<) 💦",
        ),
        "sleepy": MascotArt(
            name="bunny",
            mood="sleepy",
            art_lines=[
                r"  (\_/)   ",
                r"  ( -.-)zZ",
                r"  / >🌙   ",
                r" (  . . ) ",
                r"  o_(\_)  ",
            ],
            face="(\\_/) (-.-) zZ",
        ),
    },
    "bear": {
        "neutral": MascotArt(
            name="bear",
            mood="neutral",
            art_lines=[
                r"  ʕ •ᴥ• ʔ ",
                r"  /     \ ",
                r" ( |   | )",
                r"  (_)-(_) ",
            ],
            face="ʕ •ᴥ• ʔ",
        ),
        "happy": MascotArt(
            name="bear",
            mood="happy",
            art_lines=[
                r"  ʕ ᵔᴥᵔ ʔ*",
                r"  /  🍯  \ ",
                r" ( |   | )",
                r"  (_)-(_) ",
            ],
            face="ʕ ᵔᴥᵔ ʔ ✨",
        ),
        "worried": MascotArt(
            name="bear",
            mood="worried",
            art_lines=[
                r"  ʕ •́ᴥ•̀ ʔ ",
                r"  /     \ ",
                r" ( |   | )",
                r"  (_)-(_) ",
            ],
            face="ʕ •́ᴥ•̀ ʔ 💦",
        ),
        "sleepy": MascotArt(
            name="bear",
            mood="sleepy",
            art_lines=[
                r"  ʕ -ᴥ- ʔz",
                r"  /     \ ",
                r" ( |   | )",
                r"  (_)-(_) ",
            ],
            face="ʕ -ᴥ- ʔ zZz",
        ),
    },
    "fox": {
        "neutral": MascotArt(
            name="fox",
            mood="neutral",
            art_lines=[
                r"  /|_/|   ",
                r" ( o.o )  ",
                r"  > ^ < ~>",
                r" (  . . ) ",
                r"  \_-^-/  ",
            ],
            face="/ᐠ. ̫ .ᐟ\\",
        ),
        "happy": MascotArt(
            name="fox",
            mood="happy",
            art_lines=[
                r"  /|_/|   ",
                r" ( ^.^ )* ",
                r"  > ^ < ~>",
                r" (  . . ) ",
                r"  \_-^-/  ",
            ],
            face="/ᐠ^ ̫ ^ᐟ\\ ✨",
        ),
        "worried": MascotArt(
            name="fox",
            mood="worried",
            art_lines=[
                r"  /|_/|   ",
                r" ( O.o )💦",
                r"  > ^ < ~>",
                r" (  . . ) ",
                r"  \_-^-/  ",
            ],
            face="/ᐠo ̫ oᐟ\\ 💦",
        ),
        "sleepy": MascotArt(
            name="fox",
            mood="sleepy",
            art_lines=[
                r"  /|_/|   ",
                r" ( -.- )z ",
                r"  > ^ < ~>",
                r" (  . . ) ",
                r"  \_-^-/  ",
            ],
            face="/ᐠ- ̫ -ᐟ\\ zZ",
        ),
    },
    "penguin": {
        "neutral": MascotArt(
            name="penguin",
            mood="neutral",
            art_lines=[
                r"   (o_o)  ",
                r"  /|   |\ ",
                r"  <|   |> ",
                r"   (___)_ ",
            ],
            face="(<• )",
        ),
        "happy": MascotArt(
            name="penguin",
            mood="happy",
            art_lines=[
                r"   (^_^)~*",
                r"  /|   |\ ",
                r"  <|   |> ",
                r"   (___)_ ",
            ],
            face="(<^ ) ✨",
        ),
        "worried": MascotArt(
            name="penguin",
            mood="worried",
            art_lines=[
                r"   (;_;)  ",
                r"  /|   |\ ",
                r"  <|   |> ",
                r"   (___)_ ",
            ],
            face="(<o ) 💦",
        ),
        "sleepy": MascotArt(
            name="penguin",
            mood="sleepy",
            art_lines=[
                r"   (-.-)z ",
                r"  /|   |\ ",
                r"  <|   |> ",
                r"   (___)_ ",
            ],
            face="(<- ) zZ",
        ),
    },
    "shiba": {
        "neutral": MascotArt(
            name="shiba",
            mood="neutral",
            art_lines=[
                r"  /^ ^\   ",
                r" / ᵔᴥᵔ \  ",
                r"(   U   ) ",
                r" |  |  |~ ",
                r" (_(_(_/  ",
            ],
            face="[˚ᴥ˚]",
        ),
        "happy": MascotArt(
            name="shiba",
            mood="happy",
            art_lines=[
                r"  /^ ^\   ",
                r" / ^ᴥ^ \* ",
                r"(   U   ) ",
                r" |  |  |~ ",
                r" (_(_(_/  ",
            ],
            face="[^ᴥ^] *wag*",
        ),
        "worried": MascotArt(
            name="shiba",
            mood="worried",
            art_lines=[
                r"  /^ ^\   ",
                r" / •́ᴥ•̀\  ",
                r"(   U   ) ",
                r" |  |  |~ ",
                r" (_(_(_/  ",
            ],
            face="[•́ᴥ•̀] *whine*",
        ),
        "sleepy": MascotArt(
            name="shiba",
            mood="sleepy",
            art_lines=[
                r"  /^ ^\   ",
                r" / -ᴥ- \z ",
                r"(   U   ) ",
                r" |  |  |~ ",
                r" (_(_(_/  ",
            ],
            face="[-ᴥ-] zZ",
        ),
    },
}

# --- Plain Mode Mascots (Strictly ASCII, 100% ord(c) < 128) ---

MASCOTS_ASCII: dict[str, dict[str, MascotArt]] = {
    "cat": {
        "neutral": MascotArt("cat", "neutral", [r" /\_/\ ", r"( o.o )", r" > ^ < ", r"(___)_~"], "(=^.^=)"),
        "happy": MascotArt("cat", "happy", [r" /\_/\ ", r"( ^.^ )", r" > ^ < ", r"(___)_*"], "(=^o^=) OK"),
        "worried": MascotArt("cat", "worried", [r" /\_/\ ", r"( ;.; )", r" > ^ < ", r"(___)_?"], "(=;.;=) Err"),
        "sleepy": MascotArt("cat", "sleepy", [r" /\_/\ ", r"( -.- )", r" > ^ < ", r"(___)_z"], "(=-.-=) zZ"),
    },
    "bunny": {
        "neutral": MascotArt("bunny", "neutral", [r" (\_/) ", r" (o.o) ", r" / >*  ", r"(_(_() "], "(\\_/) (o.o)"),
        "happy": MascotArt("bunny", "happy", [r" (\_/) ", r" (^.^) ", r" / >+  ", r"(_(_() "], "(\\_/) (^.^) OK"),
        "worried": MascotArt("bunny", "worried", [r" (\_/) ", r" (O.O) ", r" / >?  ", r"(_(_() "], "(\\_/) (O.O) Err"),
        "sleepy": MascotArt("bunny", "sleepy", [r" (\_/) ", r" (-.-) ", r" / >z  ", r"(_(_() "], "(\\_/) (-.-) zZ"),
    },
    "bear": {
        "neutral": MascotArt("bear", "neutral", [r" (o_o) ", r" /| |\ ", r"( | | )", r" (_|_) "], "(o_o)"),
        "happy": MascotArt("bear", "happy", [r" (^o^) ", r" /| |\ ", r"( | | )", r" (_|_) "], "(^o^) OK"),
        "worried": MascotArt("bear", "worried", [r" (o.O) ", r" /| |\ ", r"( | | )", r" (_|_) "], "(o.O) Err"),
        "sleepy": MascotArt("bear", "sleepy", [r" (-.-) ", r" /| |\ ", r"( | | )", r" (_|_) "], "(-.-) zZ"),
    },
    "fox": {
        "neutral": MascotArt("fox", "neutral", [r" /|_/| ", r"( o.o )", r" > ^ < ", r"(___)_~"], "(o.o)"),
        "happy": MascotArt("fox", "happy", [r" /|_/| ", r"( ^.^ )", r" > ^ < ", r"(___)_~"], "(^.^) OK"),
        "worried": MascotArt("fox", "worried", [r" /|_/| ", r"( O.o )", r" > ^ < ", r"(___)_~"], "(O.o) Err"),
        "sleepy": MascotArt("fox", "sleepy", [r" /|_/| ", r"( -.- )", r" > ^ < ", r"(___)_~"], "(-.-) zZ"),
    },
    "penguin": {
        "neutral": MascotArt("penguin", "neutral", [r"  (o_o) ", r" /|   |\ ", r" <|   |>", r"  (___)_"], "(o_o)"),
        "happy": MascotArt("penguin", "happy", [r"  (^_^) ", r" /|   |\ ", r" <|   |>", r"  (___)_"], "(^_^) OK"),
        "worried": MascotArt("penguin", "worried", [r"  (;_;) ", r" /|   |\ ", r" <|   |>", r"  (___)_"], "(;_;) Err"),
        "sleepy": MascotArt("penguin", "sleepy", [r"  (-.-) ", r" /|   |\ ", r" <|   |>", r"  (___)_"], "(-.-) zZ"),
    },
    "shiba": {
        "neutral": MascotArt("shiba", "neutral", [r" /^ ^\ ", r"( o.o )", r"(  U  )", r" (_|_)~"], "[o.o]"),
        "happy": MascotArt("shiba", "happy", [r" /^ ^\ ", r"( ^.^ )", r"(  U  )", r" (_|_)~"], "[^.^] OK"),
        "worried": MascotArt("shiba", "worried", [r" /^ ^\ ", r"( O.o )", r"(  U  )", r" (_|_)~"], "[O.o] Err"),
        "sleepy": MascotArt("shiba", "sleepy", [r" /^ ^\ ", r"( -.- )", r"(  U  )", r" (_|_)~"], "[-.-] zZ"),
    },
}


def resolve_mascot_name(configured_name: str) -> str:
    """Resolve configured mascot name, picking a random mascot if 'random'."""
    clean = configured_name.strip().lower()
    if clean == "random":
        return random.choice(VALID_MASCOTS)
    if clean in VALID_MASCOTS:
        return clean
    return "cat"


def get_mascot(name: str, mood: str = "neutral", is_plain: bool = False) -> MascotArt:
    """Retrieve the mascot art for the given character name and mood."""
    target_name = resolve_mascot_name(name)
    target_mood = mood if mood in ("neutral", "happy", "worried", "sleepy") else "neutral"

    dataset = MASCOTS_ASCII if is_plain else MASCOTS_UNICODE
    animal_data = dataset.get(target_name, dataset["cat"])
    return animal_data.get(target_mood, animal_data["neutral"])


def get_reactive_face(name: str, mood: str, is_plain: bool = False) -> str:
    """Retrieve a single-line reactive expression face."""
    mascot = get_mascot(name, mood=mood, is_plain=is_plain)
    return mascot.face
