"""Extract bash templates that are paraphrases to each other."""

# builtin
from __future__ import print_function

import collections
import os, sys
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "bashlex"))

import data_tools
import sqlite3

class DBConnection(object):
    def __init__(self):
        self.conn = sqlite3.connect("bash_rewrites.db",
                                    detect_types=sqlite3.PARSE_DECLTYPES,
                                    check_same_thread=False)
        self.cursor = self.conn.cursor()

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args, **kwargs):
        self.cursor.close()
        self.conn.commit()
        self.conn.close()

    def create_schema(self):
        c = self.cursor

        c.execute("CREATE TABLE IF NOT EXISTS Rewrites (s1 TEXT, s2 TEXT)")

        self.conn.commit()

    def add_rewrite(self, pair):
        s1, s2 = pair
        c = self.cursor
        c.execute("INSERT INTO Rewrites (s1, s2) VALUES (?, ?)", (s1, s2))
        self.conn.commit()

    def get_rewrite_templates(self, s1):
        rewrites = set([s1])
        c = self.cursor
        for s1, s2 in c.execute("SELECT s1, s2 FROM Rewrites WHERE s1 = ?", (s1,)):
            rewrites.add(s2)
        return rewrites

    def get_rewrites(self, ast):
        cmd = data_tools.ast2template(
            ast, loose_constraints=True, arg_type_only=False)
        rewrites = set([cmd])
        s1 = data_tools.ast2template(ast, loose_constraints=True)
        c = self.cursor
        for s1, s2 in c.execute("SELECT s1, s2 FROM Rewrites WHERE s1 = ?", (s1,)):
            rewrites.add(data_tools.rewrite(ast, s2))
        return rewrites

    def exist_rewrite(self, pair):
        s1, s2 = pair
        c = self.cursor
        for _ in c.execute("SELECT 1 FROM Rewrites WHERE s1 = ? AND s2 = ?",
                           (s1, s2)):
            return True
        return False

def extract_rewrites(data):
    nls, cms = data
    group_pairs_by_nl = {}
    for nl, cm in zip(nls, cms):
        nl = nl.strip()
        cm = cm.strip()
        if nl.lower() == "na":
            continue
        if not nl:
            continue
        if not cm:
            continue
        nl_temp = ' '.join(data_tools.basic_tokenizer(nl.decode('utf-8')))
        if not nl_temp in group_pairs_by_nl:
            group_pairs_by_nl[nl_temp] = {}
        cm_temp = data_tools.cmd2template(cm)
        if not cm_temp in group_pairs_by_nl[nl_temp]:
            group_pairs_by_nl[nl_temp][cm_temp] = collections.defaultdict(int)
        group_pairs_by_nl[nl_temp][cm_temp][cm] += 1

    merged = set()
    nls = group_pairs_by_nl.keys()
    for i in xrange(len(nls)):
        nl = nls[i]
        cm_set = set(group_pairs_by_nl[nl].keys())
        for j in xrange(i+1, len(nls)):
            nl2 = nls[j]
            cm_set2 = set(group_pairs_by_nl[nl2].keys())
            if len(cm_set & cm_set2) >= 2:
                for cm_temp in cm_set:
                    if not cm_temp in group_pairs_by_nl[nl2]:
                        group_pairs_by_nl[nl2][cm_temp] = \
                            group_pairs_by_nl[nl][cm_temp]
                    else:
                        for cm in group_pairs_by_nl[nl][cm_temp]:
                            group_pairs_by_nl[nl2][cm_temp][cm] += \
                                group_pairs_by_nl[nl][cm_temp][cm]
                merged.add(i)

    bash_paraphrases = {}
    for i in xrange(len(nls)):
        if i in merged:
            continue
        bash_paraphrases[nls[i]] = group_pairs_by_nl[nls[i]]

    with DBConnection() as db:
        db.create_schema()
        for nl, cm_temps in sorted(bash_paraphrases.items(),
                                   key=lambda x: len(x[1]), reverse=True):
            if len(cm_temps) >= 2:
                print(nl)
                for cm_temp1 in cm_temps:
                    for cm_temp2 in cm_temps:
                        if not db.exist_rewrite((cm_temp1, cm_temp2)):
                            db.add_rewrite((cm_temp1, cm_temp2))
                            print("* {} --> {}".format(cm_temp1, cm_temp2))
                print()


def test_rewrite(cmd):
    with DBConnection() as db:
        ast = data_tools.bash_parser(cmd)
        rewrites = db.get_rewrites(ast)
        for i in xrange(len(rewrites)):
            print("rewrite %d: %s" % (i, rewrites[i]))


if __name__ == "__main__":
    nl_path = sys.argv[1]
    cm_path = sys.argv[2]

    with open(nl_path) as f:
        nls = f.readlines()
    with open(cm_path) as f:
        cms = f.readlines()

    # extract_rewrites((nls, cms))

    while True:
        try:
            cmd = raw_input("> ")
            test_rewrite(cmd)
        except EOFError as ex:
            break
