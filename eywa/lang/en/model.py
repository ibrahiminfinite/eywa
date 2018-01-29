# -*- coding: utf-8 -*-

from ...entities import DateTime, Number, PhoneNumber, Email, Url
from .filenames import vectors_file_name, vector_index_file_name, interrupt_flag_file_name
from .filenames import vocab_db_file_name, inverse_vocab_db_file_name
from .filenames import frequency_file_name, frequency_db_file_name
from.filenames import phrases_db_file_name, tokens_db_file_name
from .filenames import vector_size_file_name
from .database import Database
from .extractors import DateTimeExtractor, PhoneNumberExtractor, EmailExtractor, UrlExtractor,  NumberExtractor
from . import indexer
from numpy.core.umath_tests import inner1d
import numpy as np
import annoy
import re


extractors = [DateTimeExtractor(), PhoneNumberExtractor(), EmailExtractor(), UrlExtractor(), NumberExtractor()]

indexer.run()

with open(vector_size_file_name, 'r') as f:
    dim = int(f.read())
annoy_index = annoy.AnnoyIndex(dim, 'angular')
annoy_index.load(vector_index_file_name)
vocab_db = Database(vocab_db_file_name)
inverse_vocab_db = Database(inverse_vocab_db_file_name)
frequency_db = Database(frequency_db_file_name)
phrases_db = Database(phrases_db_file_name)
frequency_db = Database(frequency_db_file_name)
tokens_db = Database(tokens_db_file_name)


def tokenizer(X):
    return [x.strip() for x in re.split('(\W+)?', X) if x.strip()]


def split_into_sentences(text):
    orig_text = text
    text = " " + text + "  "
    text = text.replace("\n"," ")
    text = re.sub(digits + "[.]" + digits,"\\1<prd>\\2",text)
    text = re.sub(prefixes,"\\1<prd>",text)
    text = re.sub(websites,"<prd>\\1",text)
    if "Ph.D" in text: text = text.replace("Ph.D.","Ph<prd>D<prd>")
    text = re.sub("\s" + caps + "[.] "," \\1<prd> ",text)
    text = re.sub(acronyms+" "+starters,"\\1<stop> \\2",text)
    text = re.sub(caps + "[.]" + caps + "[.]" + caps + "[.]","\\1<prd>\\2<prd>\\3<prd>",text)
    text = re.sub(caps + "[.]" + caps + "[.]","\\1<prd>\\2<prd>",text)
    text = re.sub(" "+suffixes+"[.] "+starters," \\1<stop> \\2",text)
    text = re.sub(" "+suffixes+"[.]"," \\1<prd>",text)
    text = re.sub(" " + caps + "[.]"," \\1<prd>",text)
    if "”" in text: text = text.replace(".”","”.")
    if "\"" in text: text = text.replace(".\"","\".")
    if "!" in text: text = text.replace("!\"","\"!")
    if "?" in text: text = text.replace("?\"","\"?")
    text = text.replace(".",".<stop>")
    text = text.replace("?","?<stop>")
    text = text.replace("!","!<stop>")
    text = text.replace("<prd>",".")
    sentences = text.split("<stop>")
    sentences = sentences[:-1]
    sentences = [s.strip() for s in sentences]
    if not sentences:
        return [orig_text]
    return sentences


_PHRASER_THRESHOLD = 0.0004
_IGNORE_PHRASES = ['tell_me']


def phraser(X):
    num_x = len(X)
    i = 0
    output = []
    while i < num_x:
        x = X[i]
        if x in phrases_db:
            phrases = phrases_db[x]
            phrases = [vocab_db[p].split('|')[0] for p in phrases]
        else:
            phrases = [x]
        best_phrase = None
        best_phrase_prob = 0
        best_phrase_len = 0
        for phrase in phrases:
            if phrase in _IGNORE_PHRASES:
                continue
            tokens = phrase.split('_')
            if X[i : i + len(tokens)] != tokens:
                continue
            num_tokens = len(tokens)
            if num_tokens + i > num_x:
                continue
            '''
            if phrase in frequency_db:
                freq_phrase = frequency_db[phrase]
            else:
                freq_phrase = 0
            freq_tokens = []
            for t in tokens:
                if t in frequency_db:
                    freq_tokens.append(frequency_db[t])
                else:
                    freq_tokens.append(0)
            freq_tokens = np.mean(freq_tokens)
            prob = freq_phrase * num_tokens ** 3 / freq_tokens
            '''
            prob = num_tokens
            if prob > best_phrase_prob:
                best_phrase_prob = prob
                best_phrase = phrase
                best_phrase_len = num_tokens
        if best_phrase_prob >= _PHRASER_THRESHOLD:
            output.append(best_phrase)
            i += best_phrase_len
        else:
            output.append(x)
            i += 1
    return output


def get_embedding(word, sense_disambiguation='max', normalize=True, default=0):
    if '|' not in word:
        if word in tokens_db:
            tokens_idxs = tokens_db[word]
            if not tokens_idxs:
                if default == 0:
                    emb = np.zeros(dim)
                elif default is None:
                    emb = None
            elif sense_disambiguation == 'max':
                emb = annoy_index.get_item_vector(tokens_idxs[0])
            elif sense_disambiguation == 'avg':
                emb = np.mean([annoy_index.get_item_vector(i) for i in tokens_idxs], 0)
            else:
                emb = None
                for tidx in tokens_idxs:
                    sense = vocab_db[tidx].split('|')[1]
                    if sense == sense_disambiguation:
                        emb = annoy_index.get_item_vector(tidx)
                        break
                if emb is None:
                    emb = annoy_index.get_item_vector(tokens_idxs[0])
        elif '_' in word:
            embs = []
            sub_tokens = word.split('_')
            for t in sub_tokens:
                t_emb = get_embedding(t, sense_disambiguation, False, None)
                if t_emb is not None:
                    embs.append(t_emb)
            emb = np.mean(embs, 0)
        elif word in phrases_db:
            phrases_idxs = phrases_db[word]
            if sense_disambiguation == 'max':
                emb = annoy_index.get_item_vector(phrases_idxs[0])
            elif sense_disambiguation == 'avg':
                emb = np.mean([annoy_index.get_item_vector(i) for i in phrases_idxs], 0)
            else:
                emb = None
                for pidx in phrases_idxs:
                    p = vocab_db[pidx]
                    if p.split('|')[1] == sense_disambiguation:
                        emb = annoy_index.get_item_vector(pidx)
                if emb is None:
                    emb = np.mean([annoy_index.get_item_vector(i) for i in phrases_idxs], 0)
    elif word in inverse_vocab_db:
        word_index = inverse_vocab_db[word]
        emb = annoy_index.get_item_vector(word_index)
    else:
        word, sense = word.split('|')
        emb = get_embedding(word, sense, False)
    if emb is not None and normalize:
        mag = inner1d(emb, emb)
        if mag != 0:
            emb /= mag
    return emb


def get_frequency(word, sense_disambiguation='max'):
    if '|' not in word:
        if word in tokens_db:
            tokens_idxs = tokens_db[word]
            if not tokens_idxs:
                if default == 0:
                    freq = 0
            elif sense_disambiguation == 'max':
                freq = frequency_db[tokens_idxs[0]]
            elif sense_disambiguation == 'avg':
                freq = np.mean([frequency_db[i] for i in tokens_idxs])
            else:
                freq = None
                for tidx in tokens_idxs:
                    sense = vocab_db[tidx].split('|')[1]
                    if sense == sense_disambiguation:
                        freq = frequency_db[tidx]
                        break
                if freq is None:
                    freq = frequency_db[tokens_idxs[0]]
        elif '_' in word:
            first_token = word.split('_')[0]
            freq = get_frequency(first_token, sense_disambiguation)
        elif word in phrases_db:
            phrases_idxs = phrases_db[word]
            if sense_disambiguation == 'max':
                freq = frequency_db[phrases_idxs[0]]
            elif sense_disambiguation == 'avg':
                freq = np.mean([frequency_db[i] for i in tokens_idxs])
            else:
                freq = None
                for pidx in phrases_idxs:
                    p = vocab_db[pidx]
                    if p.split('|')[1] == sense_disambiguation:
                        freq = frequency_db[i]
                if freq is None:
                    freq = np.mean([frequency_db[i] for i in phrases_idxs])
    elif word in inverse_vocab_db:
        word_index = inverse_vocab_db[word]
        freq = frequency_db[word_index]
    else:
        word, sense = word.split('|')
        freq = get_frequency(word, sense, False)
    return freq


## Entity type -> embedding mapping

entity_embedding = {
    DateTime : 'time',
    Number : 'one',
    Email : 'email',
    Url : 'website',
    PhoneNumber : 'phone',
}


class Token(object):
    def __init__(self, text, entity=None):
        self.text = text
        self.entity = entity

    def __str__(self):
        return self.text

    @property
    def embedding(self):
        try:
            emb = self._embedding
            if emb is None:
                return np.zeros(dim)
            return emb
        except AttributeError:
            if self.entity:
                emb = get_embedding(entity_embedding[type(self.entity)], default=None)
            else:
                emb = get_embedding(self.text.lower(), default=None)
            self._embedding = emb
            if emb is None:
                return np.zeros(dim)
            return emb

    @property
    def type(self):
        if self.entity:
            return self.entity.type
        return None

    @property
    def in_vocab(self):
        try:
            return self._in_vocab
        except AttributeError:
            _in_vocab = any(self.embedding)
            self._in_vocab = _in_vocab
            return _in_vocab

    @property
    def frequency(self):
        try:
            return self._frequency
        except AttributeError:
            freq = get_frequency(self.text.lower())
            self._frequency = freq
            return freq

    def __eq__(self, text):
        if type(text) in (Document, Token):
            text = text.text
        return self.text == text

class Document(object):
    def __init__(self, text):
        if type(text) in (Document, Token):
            text = text.text
        self.text = text
        # Entity Extraction + tokenization
        entity_table = {}
        for ext in extractors:
            entities = ext(text)
            diff = 0
            for e in range(len(entities)):
                ent = entities[e]
                (ent_start_idx, ent_end_idx), ent_obj = ent
                ent_start_idx += diff
                ent_end_idx += diff
                ent_id = 'notokenizeentity' + 'x' * len(entity_table)
                diff += len(ent_id) - ent_end_idx + ent_start_idx + 2
                entity_table[ent_id] = ent_obj
                text_before_ent = text[:ent_start_idx]
                text_after_ent = text[ent_end_idx:]
                text = text_before_ent + ' ' + ent_id + ' ' + text_after_ent
                print(text)
        tokens = [Token(w) for w in phraser(tokenizer(text))]
        for t in tokens:
            if t.text in entity_table:
                ent = entity_table[t.text]
                t.text = ent.source_string
                t.entity = ent
        self.tokens = tokens

    def __iter__(self):
        self.iter_index = 0
        return self

    def next(self):
        if self.iter_index == len(self.tokens):
            raise StopIteration()
        token = self.tokens[self.iter_index]
        self.iter_index += 1
        return token

    def __getitem__(self, key):
        if type(key) is slice:
            tokens = self.tokens[key]
            doc = Document('')
            doc.tokens = tokens
            doc.text = ' '.join([t.text for t in tokens])
            return doc
        elif type(key) is int:
            return self.tokens[key]
        else:
            key = key.lower()
            tokens = [t for t in self.tokens if t.text.lower() == key]
            return tokens
 
    def __contains__(self, word):
        word = word.lower()
        for token in self.tokens:
            if token.text.lower() == word:
                return True
        return False

    def __len__(self):
        return len(self.tokens)

    def __str__(self):
        return self.text

    @property
    def embeddings(self):
        try:
            return self._embeddings
        except AttributeError:
            self._embeddings = np.array([t.embedding for t in self.tokens])
            return self._embeddings

    @property
    def embedding(self):
        try:
            return self._embedding
        except AttributeError:
            self._embedding = np.mean([t.embedding for t in self.tokens], 0)
            return self._embedding

    def __repr__(self):
        line1 = ''
        line2 = ''
        for w in self.tokens:
            if w.entity:
                txt1 = w.text
                txt2 = w.entity.type
                if len(txt1) > len(txt2):
                    diff = len(txt1) - len(txt2)
                    left_spaces = int(diff / 2)
                    right_spaces = diff - left_spaces
                    txt2 = ' ' * left_spaces + txt2 + ' ' * right_spaces
                elif len(txt2) > len(txt1):
                    diff = len(txt2) - len(txt1)
                    left_spaces = int(diff / 2)
                    right_spaces = diff - left_spaces
                    txt1 = ' ' * left_spaces + txt1 + ' ' * right_spaces
                line1 += txt1 + ' '
                line2 += txt2 + ' '
            else:
                txt = w.text
                line1 += txt + ' '
                line2 += ' ' * len(txt) + ' '
        return line1[:-1] + '\n' + line2[:-1]

    def __eq__(self, text):
        if type(text) in (Document, Token):
            text = text.text
        return self.text == text