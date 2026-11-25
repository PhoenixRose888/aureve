"""Membership regressions using real functions, without DB or paid AI calls."""
import ast
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


source = ast.parse((Path(__file__).parents[1] / 'server.py').read_text())
names = {'is_premium', 'enforce_limit', 'now_utc', 'complimentary_state'}
constants = {'FREE_LIMITS', 'PREMIUM_MESSAGES'}
nodes = [n for n in source.body if
         isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names or
         isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
ns = dict(os=os, datetime=datetime, timedelta=timedelta, timezone=timezone, HTTPException=HTTPException)
exec(compile(ast.Module(body=nodes, type_ignores=[]), 'server.py', 'exec'), ns)


class StylistMembershipTests(unittest.IsolatedAsyncioTestCase):
    async def check_access(self, account, allowed):
        with patch.dict(os.environ, {'TRIAL_UNLOCK_ALL': ''}):
            premium = ns['is_premium'](account)
        if allowed:
            await ns['enforce_limit']({'premium': premium}, 'stylist')
        else:
            with self.assertRaises(HTTPException) as caught:
                await ns['enforce_limit']({'premium': premium}, 'stylist')
            self.assertEqual(caught.exception.status_code, 402)

    async def test_free_account_has_no_stylist_allowance(self):
        await self.check_access({}, False)

    async def test_active_welcome_access_allows_stylist(self):
        await self.check_access({'premium_until': (datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
                                 'premium_source': 'complimentary'}, True)

    async def test_expired_welcome_access_locks_stylist(self):
        await self.check_access({'premium_until': (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                                 'premium_source': 'complimentary'}, False)

    async def test_paid_access_continues_after_welcome_period(self):
        await self.check_access({'premium_until': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                                 'complimentary_expires_at': (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                                 'premium_source': 'revenuecat'}, True)

    async def test_invalid_membership_date_does_not_unlock(self):
        await self.check_access({'premium_until': 'invalid'}, False)

    async def test_family_profile_does_not_get_primary_premium_seat(self):
        with self.assertRaises(HTTPException) as caught:
            await ns['enforce_limit']({'premium': False, 'account_premium': True, 'is_primary': False}, 'stylist')
        self.assertEqual(caught.exception.status_code, 402)
        self.assertIn('main wardrobe', caught.exception.detail)

    def test_other_free_allowances_unchanged(self):
        self.assertEqual(ns['FREE_LIMITS'], {'beauty': {'period': 'month', 'max': 1},
                                           'dressme': {'period': 'month', 'max': 5}})


if __name__ == '__main__':
    unittest.main()
