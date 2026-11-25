"""Exercise the real shortlist functions without database or model calls."""
import ast
import hashlib
import re
from pathlib import Path
from typing import List
import unittest
from types import SimpleNamespace

source = ast.parse((Path(__file__).parents[1] / 'server.py').read_text())
constants = {'FORMALITY_ORDER', '_MAIN_CATS', '_PAIR_EXCLUSIONS'}
functions = {'_items_pair', 'pairing_shortlist', 'complete_outfit', 'hydrate_photos', 'items_scope'}
nodes = [node for node in source.body if
         isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in functions or
         isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in node.targets)]
namespace = {'List': List, 'hashlib': hashlib, 're': re}
exec(compile(ast.Module(body=nodes, type_ignores=[]), 'server.py', 'exec'), namespace)
shortlist = namespace['pairing_shortlist']


class PairingShortlistTests(unittest.TestCase):
    def setUp(self):
        self.focus = {'id': 'focus-a', 'category': 'Tops', 'formality': 'Casual'}
        self.items = [
            {'id': f'{category}-{i}', 'category': category, 'name': f'Beige item {i}', 'formality': 'Casual'}
            for category in ('Bottoms', 'Shoes', 'Outerwear', 'Accessories') for i in range(20)
        ]

    def test_request_stays_bounded_and_has_unique_ids(self):
        result = shortlist(self.focus, self.items)
        self.assertEqual(len(result), 12)
        self.assertEqual(len({item['id'] for item in result}), 12)

    def test_different_focus_items_receive_different_candidates(self):
        first = {item['id'] for item in shortlist(self.focus, self.items)}
        second = {item['id'] for item in shortlist({**self.focus, 'id': 'focus-b'}, self.items)}
        self.assertNotEqual(first, second)

    def test_categories_are_balanced(self):
        result = shortlist(self.focus, self.items)
        for category in ('Bottoms', 'Shoes', 'Outerwear', 'Accessories'):
            self.assertEqual(sum(item['category'] == category for item in result), 3)

    def test_names_do_not_determine_selection(self):
        renamed = [{**item, 'name': 'Zebra renamed'} for item in self.items]
        self.assertEqual([item['id'] for item in shortlist(self.focus, self.items)],
                         [item['id'] for item in shortlist(self.focus, renamed)])

    def test_existing_pairing_exclusions_are_respected(self):
        items = [{'id': 'same', 'category': 'Tops'},
                 {'id': 'dress', 'category': 'Dresses'},
                 {'id': 'formal', 'category': 'Bottoms', 'formality': 'Formal'}]
        self.assertEqual(shortlist(self.focus, items), [])


class OutfitCompletenessTests(unittest.TestCase):
    def test_two_bottoms_and_shoes_have_no_top(self):
        items = [{'category': 'Bottoms', 'name': 'Cream skirt'},
                 {'category': 'Bottoms', 'name': 'Black trousers'},
                 {'category': 'Shoes'}]
        self.assertFalse(namespace['complete_outfit'](items))

    def test_separates_and_shoes_are_complete(self):
        self.assertTrue(namespace['complete_outfit']([{'category': c} for c in ('Tops', 'Bottoms', 'Shoes')]))

    def test_dress_and_shoes_are_complete(self):
        self.assertTrue(namespace['complete_outfit']([{'category': c} for c in ('Dresses', 'Shoes')]))

    def test_jumpsuit_in_tops_is_a_complete_one_piece(self):
        self.assertTrue(namespace['complete_outfit']([{'category': 'Tops', 'name': 'Black jumpsuit'}, {'category': 'Shoes'}]))

    def test_bodysuit_needs_a_bottom(self):
        self.assertFalse(namespace['complete_outfit']([{'category': 'Tops', 'name': 'Black bodysuit'}, {'category': 'Shoes'}]))

    def test_missing_footwear_is_incomplete(self):
        self.assertFalse(namespace['complete_outfit']([{'category': 'Tops'}, {'category': 'Bottoms'}]))


class HydrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_deleted_items_are_excluded_from_returned_live_items(self):
        captured = {}

        class Cursor:
            async def to_list(self, limit):
                return [{'id': 'live', 'photo': 'live-photo'}]

        class Collection:
            def find(self, query, projection):
                captured['query'] = query
                captured['projection'] = projection
                return Cursor()

        namespace['db'] = SimpleNamespace(items=Collection())
        items = [{'id': 'live', 'name': 'Live top'}, {'id': 'deleted', 'name': 'Deleted top'}]
        result = await namespace['hydrate_photos']({'user_id': 'wardrobe-a'}, items)
        self.assertEqual([item['id'] for item in result], ['live'])
        self.assertEqual(result[0]['photo'], 'live-photo')
        self.assertEqual(captured['query']['user_id'], 'wardrobe-a')
        self.assertEqual(captured['query']['demo'], {'$ne': True})
        self.assertNotIn('orig_photo', captured['projection'])


if __name__ == '__main__':
    unittest.main()
