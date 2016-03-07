#!/usr/bin/env python

from __future__ import print_function

import collections
import copy
import gzip
import os
import sys
sys.path.append("../../misc")
import time

from grammar import *

class Rule(object):

    def __init__(self, parent, child):
        self.parent = parent
        self.child = child

    def toString(self):
        return "{}=>{}".format(self.parent, self.child)

class Cell(object):

    def __init__(self, t, p, bp, ff):
        """
        :member terms:          new term string consumed by this cell
        :member p:              pointer to parent cell in the syntax tree
        :member backpointer:    pointer to last cell sequentially
        :member isEOF:          if cell is terminable
        :member score:          score of the partial command parse
        :member covered_words:  natural language words covered by this cell
        :member features:       features of the partial command parse up to this cell
        """
        self.term = t
        self.parent = p
        self.backpointer = bp
        self.length = bp.length + 1 if bp else 0
        self.score = bp.score + sum(ff.values()) if bp else 0
        self.covered_words = set(ff.keys())

        # INEFFICIENT
        # self.cnl_words = copy.deepcopy(bp.cnl_words) if bp else set()
        # self.lnl_words = copy.deepcopy(bp.lnl_words) if bp else set(w_uc)
        # for w in w_c:
        #     self.cnl_words.add(w)
        # for w in w_c:
        #     if w in self.lnl_words:
        #         self.lnl_words.remove(w)

        self.features = {}
        for w in ff:
            self.features["{}->{}".format(w, self.term)] = ff[w]

    # natural language words covered by the partial command up to this cell
    def cnl_words(self):
        covered_words = copy.deepcopy(self.covered_words)
        bp = self.backpointer
        while (bp):
            covered_words |= bp.covered_words
            bp = bp.backpointer
        return covered_words

    # set of features extracted from the partial command up to this cell
    def featureSet(self):
        featureSet = copy.deepcopy(self.features)
        bp = self.backpointer
        while (bp):
            featureSet.update(bp.features)
            bp = bp.backpointer
        return featureSet

    def genCommand(self):
        if self.term == Enumerator.HOLE:
            command = ["*"]
        else:
            command = [self.term]
        bp = self.backpointer
        while (bp):
            if bp.term == Enumerator.HOLE:
                command.insert(0, "*")
            else:
                command.insert(0, bp.term)
            bp = bp.backpointer
        return ' '.join(command[1:])

class Parser(Enumerator):

    def __init__(self, grammar, min_cl=2, max_cl=10):
        """
        :param grammar:
        :param min_cl: minimum number of tokens in command
        :param max_cl: maximum number of tokens in command
        """
        Enumerator.__init__(self, grammar)
        self.P2TScores = None
        self.T2PScores = None
        self.redundant_word_score = 0.0
        self.ungrounded_token_score = -1e-5
        self.min_command_length = min_cl
        self.max_command_length = max_cl

    def make_phrase_table(self, inputFile):
        self.P2TScores = collections.defaultdict(dict)
        self.T2PScores = collections.defaultdict(dict)
        with gzip.open(inputFile, 'rb') as f:
            for line in f.readlines():
                parts = line.strip().split("|||")
                nl_phrase = parts[0].strip()
                cmd_snippet = parts[1].strip()
                phi_cmd_nl, lex_cmd_nl, phi_nl_cmd, lex_nl_cmd = \
                    [float(s) for s in parts[2].split()]
                # symmetric scoring
                self.P2TScores[nl_phrase][cmd_snippet] = lex_nl_cmd
                self.T2PScores[cmd_snippet][nl_phrase] = lex_nl_cmd

    def local_score(self, term, words):
        # TODO: consider other methods for rule scoring
        covered_words = set()
        if not term in self.T2PScores:
            return {}
        fired_features = {}
        # max = 0.0
        for word in words:
            if word in self.T2PScores[term]:
                # if self.T2PScores[term][word] > max:
                #     max = self.T2PScores[term][word]
                #     covered_words.add(word)
                fired_features[word] = self.T2PScores[term][word]
        # print("local_score(covered_words){}".format(covered_words),
        #       file=sys.stderr)
        return fired_features

    def final_score(self, cell, words):
        cell.score += self.redundant_word_score * len(set(words) - cell.cnl_words())

    def parse(self, sent, top_K=50):
        words = sent.split()
        word_set = set(words)

        start_cell = Cell("__START_SYMBOL__", None, None, {})
        final_cells = []                # store tail cells of all legal commands

        print("Enumerating all commands up to length {}".format(
                self.max_command_length), file=sys.stderr)

        # DFS
        start_time = time.time()
        self.dfs(start_cell, words, final_cells)
        end_time = time.time()
        print("total # of parses: %d" % len(final_cells), file=sys.stderr)
        print("execution time: %ds" % (end_time-start_time), file=sys.stderr)

        # Rank and print all parses
        for cell in final_cells:
            self.final_score(cell, words)

        for cell in sorted(final_cells, key=lambda x:x.score, reverse=True)[:top_K]:
            print("{}:\t\t{}\t{}\t{}\t{}\t{}".format(cell.genCommand(), cell.score,
                    cell.length, cell.cnl_words(), word_set-cell.cnl_words(), cell.featureSet()),
                    file=sys.stderr)

    def dfs(self, cell, words, final_cells):

        term = cell.term

        # skip <EOF> character
        if term == Enumerator.EOF:
            return

        # TODO: handle compound commands
        if term == "|":
            return

        # yield legal command
        if cell.length > self.min_command_length and self.allow_eof():
            final_cells.append(cell)

        # maximum depth reached, backtrack
        if cell.length == self.max_command_length:
            return

        # update enumerator
        if term != "__START_SYMBOL__":
            if self.allows(term):
                # print("{}".format(self.legal_tokens()), file=sys.stderr)
                self.push(term)
            else:
                # print("Not allowed {}".format(self.legal_tokens()), file=sys.stderr)
                # print("Error: shouldn't happen!", file=sys.stderr)
                sys.exit(1)
                return

        # look ahead one step
        for term in self.legal_tokens():
            fired_features = self.local_score(term, words)
            child_cell = Cell(term, None, cell, fired_features)
            self.dfs(child_cell, words, final_cells)

        if term != "__START_SYMBOL__":
            self.pop()
        return


if __name__ == "__main__":
    nl_cmd = sys.argv[1]

    simple_grammar = load_syntax([os.path.join(os.path.dirname(__file__),
                                               "..", "..", "data", "primitive_cmds_grammar.json")])
    grammar = make_full_grammar(simple_grammar, max_pipeline_depth=3)

    # minimum number of tokens in command = 2
    # maximum number of tokens in command = 3
    parser = Parser(grammar, 2, 3)
    parser.make_phrase_table(os.path.join(os.path.dirname(__file__),
                                           "..", "..", "data", "phrase-table.gz"))

    parser.parse(nl_cmd)