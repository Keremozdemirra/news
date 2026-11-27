"""Peer groups for Who is this?: people a reader would accept as fair alternatives to one another.

A quiz once set a woman's portrait (Kathy Hochul) against Jared Kushner, Thariq Shihipar and Donald Trump: the
photo gave the answer away and one name was unknown to almost everyone. Each group below holds widely known people
of one role, split by how they present in public portraits, so the options look alike and every name is fair.
A person in no group gets no portrait quiz, and nobody outside these lists is ever used as filler.

Roles and names checked 2026-11-27; a former office holder stays in the group of the role readers know them for.
Review once a year: governments and boards change.
"""
import unicodedata

# role -> {"f": [...], "m": [...]}
GROUPS = {
    "US governors": {
        "f": ["Kathy Hochul", "Gretchen Whitmer", "Maura Healey", "Sarah Huckabee Sanders", "Katie Hobbs", "Kelly Ayotte"],
        "m": ["Gavin Newsom", "Josh Shapiro", "Ron DeSantis", "Greg Abbott", "JB Pritzker", "Wes Moore"],
    },
    "central bankers": {
        "f": ["Christine Lagarde", "Elvira Nabiullina", "Michele Bullock", "Michelle Bowman", "Lisa Cook"],
        "m": ["Jerome Powell", "Andrew Bailey", "Kazuo Ueda", "Pablo Hernández de Cos", "Pan Gongsheng", "Tiff Macklem",
              "Joachim Nagel", "Christopher Waller"],
    },
    "heads of government": {
        "f": ["Giorgia Meloni", "Ursula von der Leyen", "Claudia Sheinbaum", "Sanae Takaichi", "Mette Frederiksen"],
        "m": ["Donald Trump", "Emmanuel Macron", "Keir Starmer", "Friedrich Merz", "Xi Jinping", "Narendra Modi",
              "Mark Carney", "Recep Tayyip Erdoğan", "Pedro Sánchez", "Luiz Inácio Lula da Silva", "Volodymyr Zelensky"],
    },
    "US administration": {
        "f": ["Pam Bondi", "Kristi Noem", "Susie Wiles", "Tulsi Gabbard", "Karoline Leavitt", "Brooke Rollins"],
        "m": ["JD Vance", "Marco Rubio", "Scott Bessent", "Howard Lutnick", "Pete Hegseth", "Jared Kushner", "Steve Witkoff"],
    },
    "tech leaders": {
        "f": ["Lisa Su", "Gwynne Shotwell", "Mira Murati", "Fidji Simo", "Ruth Porat", "Safra Catz", "Daniela Amodei"],
        "m": ["Jensen Huang", "Sam Altman", "Satya Nadella", "Sundar Pichai", "Tim Cook", "Mark Zuckerberg", "Elon Musk",
              "Dario Amodei", "Andy Jassy", "Demis Hassabis", "Jeff Bezos"],
    },
    "finance leaders": {
        "f": ["Jane Fraser", "Abigail Johnson", "Ana Botín", "Cathie Wood", "Kristalina Georgieva"],
        "m": ["Jamie Dimon", "David Solomon", "Larry Fink", "Ted Pick", "Brian Moynihan", "Warren Buffett", "Ken Griffin"],
    },
    "industry chiefs": {
        "f": ["Mary Barra", "Julie Sweet", "Emma Walmsley", "Belén Garijo"],
        "m": ["Bob Iger", "Doug McMillon", "Kelly Ortberg", "Jim Farley", "Oliver Blume", "Bernard Arnault"],
    },
}


def norm(name):
    flat = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return " ".join(flat.replace(".", " ").split())


def place(name):
    """(role, presentation) of a listed person, or None."""
    n = norm(name)
    for role, sides in GROUPS.items():
        for side, names in sides.items():
            if n in {norm(x) for x in names}:
                return role, side
    return None


def peers(name):
    """People of the same role and presentation, never the person or anyone sharing their surname; [] if unlisted."""
    at = place(name)
    if not at:
        return []
    last = norm(name).split()[-1]
    return [x for x in GROUPS[at[0]][at[1]] if norm(x) != norm(name) and norm(x).split()[-1] != last]
