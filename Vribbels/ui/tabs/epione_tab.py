"""The Epione tab: each combatant's counseling at the Epione Centre --
what is left to pick, and which option to pick next.

The left column lists every combatant held, with its options picked
against its total. Picking one shows its three scenarios to the right,
a row each: the scenario's title, how many of its options are picked,
the line the counseling opens on, then a card per opener, two the game
shows on the left and two on the right, each with its two follow-ups
and the cure result each leads to. A picked option is dimmed, one whose
reward waits to be claimed orange.

**Clicking an opener marks it as offered.** Mark the two the game
offers, one each side, and each card says how many whiffs -- counselings
of this scenario offering nothing new -- are to come if it is picked;
the fewer is green, with the follow-up to take. A combatant broken down
in a Chaos run, and so counseled next, is red in the list, and a newly
broken one is selected for you.

`epione.combatants` and `epione.advice` read and weigh; this only draws.
`docs/epione.md` has both.
"""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

import epione

from ..base_tab import BaseTab
from ..scaling import px, px_after, px_spans
from ..utils.tab_header import make_heading
from ..utils.tooltip import Tooltip
from ..utils.type_ahead import TypeAhead, find
from .checklist_tab import (BLOCK_PAD, COLUMNS_PADX, COLUMNS_PADY,
                            HEADING_COUNTDOWN_DROP, HEADING_COUNTDOWN_FONT,
                            HEADING_COUNTDOWN_GAP, HEADING_GAP, ROW_FONT,
                            ROW_PITCH)

# The list: (column id, heading, width at 100%, anchor). Wide enough for
# `Heidemarie` and for `Completed` in the list's own font.
LIST_COLUMNS = (("name", "Combatant", 110, tk.W),
                ("done", "Completed", 78, tk.CENTER))
# A row's colour, by what it says: broken down and counseled next, a
# reward waiting to be claimed, nothing left at all. One tag a row,
# the first that applies.
ROW_AWAITING = "awaiting"
ROW_UNCLAIMED = "unclaimed"
ROW_FINISHED = "finished"
ROW_COLOURS = {ROW_AWAITING: "red", ROW_UNCLAIMED: "orange",
               ROW_FINISHED: "green"}
# What the Completed column says for a combatant the client gives no
# counseling.
NO_COUNSELING = "-"

# The two columns, the list and the counseling, sit as two content
# frames do: the list's box against the counseling's.
LIST_GAP = 4            # spacing: content frame -> content frame -- tree, frame ↔
# The list's top against the tab strip. The heading beside it reaches
# the same distance through its own box's corrections.
LIST_TOP = 6            # spacing: tab list -> first element -- tab, tree ↕
# The two columns' feet against the window's, the rest of the 4 the
# tab's frame begins with its own 2 (`COLUMNS_PADY`).
COLUMNS_FOOT = 4        # spacing: content frame -> content frame -- tree, frame ↕

# The cards of one scenario side by side: two filled boxes, as two
# content frames sit. The two the game shows on the left stand apart
# from the two on the right, as groups of controls do.
CARD_GAP = 4            # spacing: content frame -> content frame -- frame, frame ↔
SIDE_GAP = 16           # spacing: control group ↔ control group -- frame, frame ↔
# Every pad below is what the rule's distance leaves once a Label's own
# box has spent its part, read off the rendered tab: a Label's text sits
# inside a border and a padding of its own, and its line box reaches
# above its capitals and below its baseline.
#
# The heading above the first scenario's title, on the Galactic Disaster
# tab's levers: 16 from baseline to capital. A pixel under its
# `HEADING_GAP + ROW_PITCH`, a Label carrying one more above its capitals
# than a Text's first line does.
FIRST_SCENARIO_GAP = HEADING_GAP + ROW_PITCH - 1
# A scenario's title above its cards, as a panel's title above it: the
# title's line box spends the whole 5.
TITLE_TO_CARDS = 0      # spacing: title above, element below -- label, frame ↕
# One scenario's cards above the next one's title, text under a panel.
CARDS_TO_TITLE = 4      # spacing: panel ↕ unrelated label -- frame, label ↕
# The note under the last scenario's cards, the same.
CARDS_TO_NOTE = 3       # spacing: panel ↕ unrelated label -- frame, label ↕
# A scenario's title, its count and the line it opens on: a label and
# what it labels, then the block's title and its subtext.
TITLE_TO_COUNT = 0      # spacing: label ↔ its element -- label, label ↔
COUNT_TO_LINE = 10      # spacing: heading ↔ element -- label, label ↔
# The heading's count and the status beside it, as `make_tab_header`'s
# subtitle sits from its heading.
COUNT_TO_STATUS = 10    # spacing: heading ↔ element -- label, label ↔

# Inside a card: the words' inset from the card's edge on every side,
# the first line's capitals as its top, which its line box already
# sets 4 down.
CARD_PADX = 4           # spacing: border edge -> first non-button element -- frame, run ↔
CARD_PADY = 0           # spacing: border edge -> first non-button element -- frame, run ↕
# One option against the next. Each is a block of wrapped lines, so they
# part at the Checklist's block division, as the Galactic Disaster tab's
# requirements do, and not at its row pitch.
OPTION_PITCH = ROW_PITCH + BLOCK_PAD
# A follow-up's cure result against its words: a value and what it
# belongs to. Between the two tab stops, the `%`'s ink stopping a pixel
# short of its advance.
RESULT_GAP = 4          # spacing: label ↔ its element -- run, run ↔

# One tag per line for its `spacing1`, as on the Checklist: two tags
# setting one option resolve by priority, not sum.
FIRST_TAG = "first"
OPTION_TAG = "option"
LINE_PITCH = {FIRST_TAG: 0, OPTION_TAG: OPTION_PITCH}
# What an option's words are drawn as: its state, then the advice over
# it. Created in this order, so a later one wins where two set a colour.
NEW_TAG = "new"
PICKED_TAG = "picked"
UNCLAIMED_TAG = "unclaimed"
ADVISED_TAG = "advised"
OPENER_TAG = "opener"
WHIFF_TAG = "whiffs"
STATE_COLOURS = {NEW_TAG: "fg", PICKED_TAG: "fg_dim",
                 UNCLAIMED_TAG: "orange", ADVISED_TAG: "green"}
# A card's fill, and an offered card's: the app's selected row.
CARD_FILL = "bg_light"
OFFERED_FILL = "select"

# What a card's last line says once the game's offer is marked.
WHIFFS = "%.2f whiffs to come"
WHIFFS_ADVISED = "Pick this: %.2f whiffs to come"
NOTHING_NEW = "Nothing new here"
NOTHING_NEW_ADVISED = "Nothing new: best cure %d%%"
WHIFFS_TIP = ("Whiffs: counselings of this scenario expected to offer "
              "only options already picked, before every one in it is, "
              "if this opener is picked now and the best one after it "
              "every time.")
RESULT = "%d%%"
WIDEST_RESULT = "100%"

# What the counseling column says around the scenarios.
NOTE = ("Click the two openers the game offers, the one on its left and "
        "the one on its right, to see which to pick.")
NOTE_ANY_TWO = ("Click the two openers the game offers to see which to "
                "pick.")
AWAITING = "Awaiting counseling"
LEFT_TO_EARN = "%s left to earn"
TO_CLAIM = "%s to claim in the Counseling Records"
NO_CAPTURE = "No capture loaded: log in with the capture running."
NOT_KNOWN = "The game client gives %s no counseling."


def _reward_words(rewards):
    """`{item: count}` as the game's words, `480 Crystals`."""
    from game_data.constants import item_names
    names = item_names()
    return ", ".join("%d %s" % (count, names.get(item, "item %s" % item))
                     for item, count in sorted(rewards.items()) if count)


class EpioneTab(BaseTab):
    """Each combatant's counseling, and which option to pick."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        self._tips = Tooltip(self.colors)
        self._seek = TypeAhead()
        # {res_id: Combatant}, and {res_id: name} for the combatants the
        # client gives no counseling; the list's rows, in its order.
        self._people = {}
        self._bare = {}
        self._order = []
        self._sort = ("name", False)
        self._shown = None
        # The res_ids broken down at the last refresh: one appearing
        # since is selected.
        self._awaiting = set()
        # {"scenario": index, "L": number, "R": number} or with
        # "picks": [numbers] under ANY_TWO: the openers marked offered.
        self._offered = {}
        # The selected combatant's options picked when its offer was
        # marked: a counseling in between makes the marks stale.
        self._marked_at = None
        # [(frame, head labels, [card Texts])], one per scenario shown.
        self._blocks = []
        self._drawn = {}
        self.setup_ui()
        self.refresh_epione()
        # **NOT redundant with the load paths:** a refresh while another
        # tab is showing reads the data and skips the drawing.
        self.when_shown(self.refresh_epione)

    # ------------------------------------------------------------ build

    def setup_ui(self):
        """Build the Epione tab UI."""
        # **Created first**: the audit reaches the columns through the
        # tab's first child.
        columns = ttk.Frame(self.frame)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        columns.pack(fill=tk.BOTH, expand=True, padx=px(COLUMNS_PADX),
                     pady=px(COLUMNS_PADY))
        columns.grid_rowconfigure(0, weight=1)
        columns.grid_columnconfigure(1, weight=1)
        self._build_list(columns)
        detail = ttk.Frame(columns)
        # spacing: content frame -> content frame -- tree, frame ↔
        # spacing: content frame -> content frame -- frame, frame ↕
        detail.grid(row=0, column=1, sticky="nsew",
                    padx=(px(LIST_GAP), 0),
                    pady=(0, px_after(COLUMNS_PADY[1],
                                      COLUMNS_FOOT - COLUMNS_PADY[1])))
        self._detail = detail
        head = ttk.Frame(detail)
        head.pack(fill=tk.X)
        self._heading = make_heading(head, "")
        self._heading.pack(side=tk.LEFT, anchor=tk.S)
        self._count = ttk.Label(head, text="", font=HEADING_COUNTDOWN_FONT)
        # spacing: heading ↔ element -- heading, label ↔
        # spacing: heading ↔ element -- heading, label ↕
        self._count.pack(side=tk.LEFT, anchor=tk.S,
                         padx=px((HEADING_COUNTDOWN_GAP, 0)),
                         pady=px((0, HEADING_COUNTDOWN_DROP)))
        self._status = ttk.Label(head, text="", font=ROW_FONT,
                                 foreground=self.colors["fg_dim"])
        # spacing: header subtext -- label, label ↔
        # spacing: heading ↔ element -- label, label ↔
        self._status.pack(side=tk.LEFT, anchor=tk.S,
                          padx=px((COUNT_TO_STATUS, 0)),
                          pady=px((0, HEADING_COUNTDOWN_DROP)))
        self._scenarios = ttk.Frame(detail)
        # spacing: exception -- panel ↕ unrelated label -- heading, label ↕
        self._scenarios.pack(fill=tk.BOTH, expand=True,
                             pady=px((FIRST_SCENARIO_GAP, 0)))
        self._note = ttk.Label(detail, text="", font=ROW_FONT,
                               foreground=self.colors["fg_dim"])
        # spacing: panel ↕ unrelated label -- frame, label ↕
        self._note.pack(anchor=tk.W, pady=px((CARDS_TO_NOTE, 0)))
        bold = tkfont.Font(font=ROW_FONT)
        bold.configure(weight="bold")
        # **Held**: a named font Tk deletes once the Python object goes.
        self._bold = bold
        self._row_font = tkfont.Font(font=ROW_FONT)

    def _build_list(self, parent):
        holder = ttk.Frame(parent)
        # spacing: tab list -> first element -- tab, tree ↕
        # spacing: content frame -> content frame -- tree, frame ↕
        holder.grid(row=0, column=0, sticky="ns",
                    pady=(px(LIST_TOP), px_after(
                        COLUMNS_PADY[1], COLUMNS_FOOT - COLUMNS_PADY[1])))
        tree = ttk.Treeview(holder, columns=[c[0] for c in LIST_COLUMNS],
                            show="headings", selectmode="browse")
        bar = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        # The scrollbar packed FIRST, so the list's columns cannot take
        # its width.
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(side=tk.LEFT, fill=tk.Y)
        for (key, title, _width, anchor), width in zip(
                LIST_COLUMNS, px_spans([c[2] for c in LIST_COLUMNS])):
            tree.heading(key, text=title, anchor=anchor,
                         command=lambda k=key: self._sort_by(k))
            tree.column(key, width=width, minwidth=width, anchor=anchor,
                        stretch=False)
        for tag, colour in ROW_COLOURS.items():
            tree.tag_configure(tag, foreground=self.colors[colour])
        tree.bind("<<TreeviewSelect>>", self._on_select)
        tree.bind("<KeyPress>", self._on_key)
        self._tree = tree

    def _block(self, index):
        """The `index`-th scenario's row: its title line and its four
        cards. Built the first time a combatant needs it, then kept."""
        while len(self._blocks) <= index:
            at = len(self._blocks)
            frame = ttk.Frame(self._scenarios)
            # spacing: panel ↕ unrelated label -- frame, label ↕
            frame.pack(fill=tk.BOTH, expand=True,
                       pady=px((CARDS_TO_TITLE if at else 0, 0)))
            head = ttk.Frame(frame)
            head.pack(fill=tk.X)
            title = ttk.Label(head, text="", font=self._bold)
            title.pack(side=tk.LEFT, anchor=tk.S)
            count = ttk.Label(head, text="", font=ROW_FONT)
            # spacing: label ↔ its element -- label, label ↔
            count.pack(side=tk.LEFT, anchor=tk.S,
                       padx=px((TITLE_TO_COUNT, 0)))
            line = ttk.Label(head, text="", font=ROW_FONT,
                             foreground=self.colors["fg_dim"])
            # spacing: heading ↔ element -- label, label ↔
            line.pack(side=tk.LEFT, anchor=tk.S,
                      padx=px((COUNT_TO_LINE, 0)))
            cards = ttk.Frame(frame)
            # spacing: title above, element below -- label, frame ↕
            cards.pack(fill=tk.BOTH, expand=True,
                       pady=px((TITLE_TO_CARDS, 0)))
            cards.grid_rowconfigure(0, weight=1)
            texts = []
            for slot in range(4):
                # Cards in the even columns, the gaps in the odd ones as
                # fixed spacers: a gap padded inside a cell of the
                # uniform group would narrow that card by the gap.
                cards.grid_columnconfigure(2 * slot, weight=1,
                                           uniform="cards")
                if slot:
                    gap = SIDE_GAP if slot == 2 else CARD_GAP
                    # spacing: content frame -> content frame -- frame, frame ↔
                    # spacing: control group ↔ control group -- frame, frame ↔
                    cards.grid_columnconfigure(2 * slot - 1, minsize=px(gap))
                text = self._card(cards)
                text.grid(row=0, column=2 * slot, sticky="nsew")
                text.bind("<Button-1>",
                          lambda _e, s=at, c=slot: self._on_card(s, c))
                texts.append(text)
            self._blocks.append((frame, (title, count, line), texts))
        return self._blocks[index]

    def _card(self, parent):
        """One opener's card: a Text of its options, filled."""
        text = tk.Text(
            parent, wrap=tk.WORD, width=1, height=1, bd=0,
            highlightthickness=px(0),
            # spacing: border edge -> first non-button element -- frame, run ↔↕
            padx=px(CARD_PADX), pady=px(CARD_PADY),
            bg=self.colors[CARD_FILL], fg=self.colors["fg"], font=ROW_FONT,
            # Selectable but never focusable, and no insertion cursor:
            # a click marks the card, and nothing invites typing.
            takefocus=0, insertwidth=px(0), cursor="hand2")
        # spacing: exception -- label row -> label row -- run, run ↕
        for tag, pitch in LINE_PITCH.items():
            text.tag_configure(tag, spacing1=px(pitch))
        for tag, colour in STATE_COLOURS.items():
            text.tag_configure(tag, foreground=self.colors[colour])
        text.tag_configure(OPENER_TAG, font=self._bold)
        self._tips.bind_tag(text, WHIFF_TAG, WHIFFS_TIP)
        text.config(state=tk.DISABLED)
        return text

    # ----------------------------------------------------------- update

    def refresh_epione(self):
        """Read the loaded snapshot and draw it. Called after every load,
        after the game client is read, and whenever the tab is shown.
        Nothing here records, so a hidden tab waits to be shown."""
        if self.is_hidden():
            return
        raw = getattr(self.optimizer, "raw_data", None) or {}
        owned = {name: info.res_id for name, info in (getattr(
            self.optimizer, "character_info", None) or {}).items()
            if getattr(info, "res_id", None)}
        people = epione.combatants(raw, owned)
        self._people = {c.res_id: c for c in people}
        self._bare = {res_id: name for name, res_id in owned.items()
                      if res_id not in self._people}
        awaiting = {c.res_id for c in people if c.awaiting}
        newly = sorted(awaiting - self._awaiting,
                       key=lambda r: self._people[r].name)
        self._awaiting = awaiting
        self._fill_list()
        if newly:
            self._select(newly[0])
        elif self._shown not in self._people and self._shown not in self._bare:
            self._select(self._order[0] if self._order else None)
        else:
            self._draw()

    def _fill_list(self):
        key, reverse = self._sort
        rows = [(res_id, c.name, c.done, c.total)
                for res_id, c in self._people.items()]
        rows += [(res_id, name, None, None)
                 for res_id, name in self._bare.items()]
        if key == "done":
            rows.sort(key=lambda r: (r[3] is None,
                                     (r[2] or 0) / (r[3] or 1), r[1]),
                      reverse=reverse)
        else:
            rows.sort(key=lambda r: r[1].lower(), reverse=reverse)
        listed = tuple((r[0], r[1], r[2], r[3], self._row_tag(r[0]))
                       for r in rows)
        if self._drawn.get("list") == listed:
            return
        self._drawn["list"] = listed
        tree = self._tree
        tree.delete(*tree.get_children())
        for res_id, name, done, total, tag in listed:
            tree.insert("", tk.END, iid=str(res_id), tags=(tag,) if tag else (),
                        values=(name, NO_COUNSELING if total is None
                                else "%d/%d" % (done, total)))
        self._order = [r[0] for r in listed]
        if self._shown is not None and tree.exists(str(self._shown)):
            tree.selection_set(str(self._shown))

    def _row_tag(self, res_id):
        person = self._people.get(res_id)
        if person is None:
            return None
        if person.awaiting:
            return ROW_AWAITING
        if person.unclaimed:
            return ROW_UNCLAIMED
        if not person.left:
            return ROW_FINISHED
        return None

    def _sort_by(self, key):
        same = self._sort[0] == key
        self._sort = (key, not self._sort[1] if same else key == "done")
        self._fill_list()

    def _select(self, res_id):
        tree = self._tree
        if res_id is not None and tree.exists(str(res_id)):
            # Fires <<TreeviewSelect>>, which draws.
            tree.selection_set(str(res_id))
            tree.see(str(res_id))
        self._show(res_id)

    def _on_select(self, _event=None):
        chosen = self._tree.selection()
        if chosen:
            self._show(int(chosen[0]))

    def _on_key(self, event):
        """Type-ahead, as the Combatants list has it."""
        hit = self._seek.key(event.char)
        if hit is None:
            return None
        names = [self._tree.set(iid, "name")
                 for iid in self._tree.get_children()]
        chosen = self._tree.selection()
        current = (self._tree.index(chosen[0]) if chosen else -1)
        index = find(names, *hit, current=current)
        if index is not None:
            self._select(self._order[index])
        return "break"

    def _show(self, res_id):
        if res_id != self._shown:
            self._offered = {}
            self._marked_at = None
        self._shown = res_id
        self._draw()

    def _on_card(self, scenario, slot):
        """Mark or unmark the opener a card shows as one the game
        offers. Under `ONE_PER_SIDE` it takes its side's mark."""
        person = self._people.get(self._shown)
        if person is None or scenario >= len(person.scenarios):
            return "break"
        opener = person.scenarios[scenario].openers[slot].option
        offered = self._offered
        if offered.get("scenario") != scenario:
            offered = {"scenario": scenario}
        if epione.PAIRING == epione.ANY_TWO:
            picks = list(offered.get("picks", ()))
            if opener.number in picks:
                picks.remove(opener.number)
            else:
                picks = (picks + [opener.number])[-2:]
            offered["picks"] = picks
        elif offered.get(opener.side) == opener.number:
            del offered[opener.side]
        else:
            offered[opener.side] = opener.number
        self._offered = offered
        self._marked_at = person.done
        self._draw()
        return "break"

    def _offered_pair(self, person):
        """(scenario index, (opener, opener)) once two are marked, else
        None. A counseling since they were marked unmarks them."""
        offered = self._offered
        if not offered or self._marked_at != person.done:
            self._offered = {}
            return None
        picks = (offered.get("picks") if epione.PAIRING == epione.ANY_TWO
                 else [offered[s] for s in "LR" if s in offered])
        if len(picks or ()) != 2:
            return None
        return offered["scenario"], tuple(picks)

    # ------------------------------------------------------------ draw

    def _draw(self):
        person = self._people.get(self._shown)
        if person is None:
            name = self._bare.get(self._shown)
            self._heading.config(text=name or "")
            self._count.config(text="")
            self._status.config(text="", foreground=self.colors["fg_dim"])
            self._note.config(text=NOT_KNOWN % name if name
                              else NO_CAPTURE if not self._order else "")
            for frame, _head, _texts in self._blocks:
                frame.pack_forget()
            self._drawn.pop("cards", None)
            return
        self._heading.config(text=person.name)
        self._count.config(
            text="%d/%d" % (person.done, person.total),
            foreground=self.colors["orange" if person.unclaimed
                                   else "green" if not person.left
                                   else "fg"])
        said = [AWAITING] if person.awaiting else []
        if person.left:
            said.append(LEFT_TO_EARN % _reward_words(person.left))
        if person.unclaimed:
            said.append(TO_CLAIM % _reward_words(person.unclaimed))
        self._status.config(text=". ".join(said),
                            foreground=self.colors["red" if person.awaiting
                                                   else "fg_dim"])
        self._note.config(text=NOTE if epione.PAIRING == epione.ONE_PER_SIDE
                          else NOTE_ANY_TWO)
        pair = self._offered_pair(person)
        for index, scenario in enumerate(person.scenarios):
            frame, head, texts = self._block(index)
            if not frame.winfo_manager():
                # spacing: panel ↕ unrelated label -- frame, label ↕
                frame.pack(fill=tk.BOTH, expand=True,
                           pady=px((CARDS_TO_TITLE if index else 0, 0)))
            title, count, line = head
            title.config(text=scenario.title)
            count.config(text="%d/%d" % (scenario.done, scenario.total))
            line.config(text=scenario.line)
            advice = None
            if pair is not None and pair[0] == index:
                advice = epione.advice(scenario, pair[1])
            for slot, opener in enumerate(scenario.openers):
                self._fill_card(texts[slot], person, opener, advice)
        for frame, _head, _texts in self._blocks[len(person.scenarios):]:
            frame.pack_forget()

    def _fill_card(self, text, person, opener, advice):
        """One card's options, and its whiff line where its opener is
        marked offered. Touched only where it changed."""
        number = opener.option.number
        offered = advice is not None and number in advice.whiffs
        advised = offered and advice.opener == number
        lines = [(self._state(opener.option, advised), OPENER_TAG,
                  "%s: %s" % (opener.option.label, opener.option.words))]
        for kid in opener.follow_ups:
            lines.append((self._state(
                kid, advised and advice.follow_up == kid.number), None,
                "\t%s\t%s: %s" % (RESULT % min(kid.result, 100), kid.label,
                                  kid.words)))
        if offered:
            whiffs = advice.whiffs[number]
            if advice.whiff:
                best = max(k.result for k in opener.follow_ups)
                words = (NOTHING_NEW_ADVISED % min(best, 100) if advised
                         else NOTHING_NEW)
            elif whiffs is None:
                words = NOTHING_NEW
            else:
                words = (WHIFFS_ADVISED if advised else WHIFFS) % whiffs
            lines.append((ADVISED_TAG if advised else PICKED_TAG, WHIFF_TAG,
                          words))
        fill = self.colors[OFFERED_FILL if offered or self._is_marked(
            person, opener) else CARD_FILL]
        drawn = (tuple(lines), fill)
        key = ("card", id(text))
        if self._drawn.get(key) == drawn:
            return
        self._drawn[key] = drawn
        # Two right-aligned results line up on their `%`, and a follow-up's
        # wrapped lines hang under its words. Measured, so not through
        # `px`; the gap is.
        result = self._row_font.measure(WIDEST_RESULT)
        words_at = result + px(RESULT_GAP)
        # spacing: label ↔ its element -- run, run ↔
        text.config(state=tk.NORMAL, bg=fill,
                    tabs=(result, tk.RIGHT, words_at, tk.LEFT))
        text.tag_configure("follow_up", lmargin2=words_at)
        text.delete("1.0", tk.END)
        for index, (state, kind, words) in enumerate(lines):
            tags = [FIRST_TAG if index == 0 else OPTION_TAG, state]
            if kind:
                tags.append(kind)
            elif index:
                tags.append("follow_up")
            text.insert(tk.END, ("\n" if index else "") + words, tuple(tags))
        text.config(state=tk.DISABLED)

    def _is_marked(self, person, opener):
        """Whether `opener` is marked offered while its pair is not yet
        whole: one mark shows as soon as it is made."""
        offered = self._offered
        if not offered or self._marked_at != person.done:
            return False
        scenario = offered.get("scenario")
        if scenario is None or scenario >= len(person.scenarios) \
                or opener not in person.scenarios[scenario].openers:
            return False
        number = opener.option.number
        return number in (offered.get("picks") or ()) \
            or offered.get(opener.option.side) == number

    @staticmethod
    def _state(option, advised):
        if advised:
            return ADVISED_TAG
        if option.picked and not option.claimed:
            return UNCLAIMED_TAG
        return PICKED_TAG if option.picked else NEW_TAG
