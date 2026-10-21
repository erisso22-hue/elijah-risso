import io
import json
import unittest
from unittest.mock import patch
import accounts
import supabase_accounts as S

ENV = {'SUPABASE_URL':'https://example.supabase.co', 'SUPABASE_PUBLISHABLE_KEY':'sb_publishable_test_only'}
USER = {'id':'11111111-1111-1111-1111-111111111111','email':'test@example.invalid'}
SESSION = {'access_token':'test-access', 'refresh_token':'test-refresh','expires_in':3600,'user':USER}
DATA = {'logs':[],'checkins':{},'settings':{'calorieGoals':[]}}

class Handler:
    def __init__(self, method='GET', body=None, cookie='', origin=None):
        self.command=method
        raw=json.dumps(body or {}).encode()
        self.headers={'Host':'app.example.invalid','Content-Length':str(len(raw)), 'X-Forwarded-Proto':'https'}
        if cookie:self.headers['Cookie']=cookie
        if origin:self.headers['Origin']=origin
        self.rfile=io.BytesIO(raw)
        self.wfile=io.BytesIO()
        self.sent=[]
    def send_response(self,status):self.status=status
    def send_header(self,k,v):self.sent.append((k,v))
    def end_headers(self):pass
    def result(self):return json.loads(self.wfile.getvalue())

@patch.dict('os.environ',ENV)
class SupabaseTests(unittest.TestCase):
    def test_login_keeps_tokens_out_of_json_and_sets_secure_http_only_cookies(self):
        h=Handler('POST',{'email':'test@example.invalid','password':'a-valid-password'})
        with patch.object(S,'request',return_value=SESSION):S.handle(h,'/api/login',accounts.valid_data)
        self.assertEqual(h.status,200)
        self.assertNotIn('test-access',h.wfile.getvalue().decode())
        cookies=[value for name,value in h.sent if name=='Set-Cookie']
        self.assertEqual(len(cookies),2)
        self.assertTrue(all('HttpOnly' in c and 'Secure' in c for c in cookies))

    def test_signup_can_require_email_confirmation_without_claiming_signed_in(self):
        h=Handler('POST',{'email':'test@example.invalid','password':'a-valid-password'},origin='https://app.example.invalid')
        with patch.object(S,'request',return_value={'user':USER}) as call:S.handle(h,'/api/register',accounts.valid_data)
        self.assertIsNone(h.result()['email'])
        self.assertTrue(h.result()['confirmationRequired'])
        self.assertIn('redirect_to=',call.call_args.args[1])

    def test_anonymous_request_cannot_read_data(self):
        h=Handler()
        with patch.object(S,'request') as call:S.handle(h,'/api/data',accounts.valid_data)
        self.assertEqual(h.status,401)
        call.assert_not_called()

    def test_data_request_uses_verified_user_and_access_token(self):
        h=Handler(cookie='ds_access=test-access')
        with patch.object(S,'request',side_effect=[USER,[{'data':DATA,'revision':3}]]) as call:S.handle(h,'/api/data',accounts.valid_data)
        self.assertEqual(h.status,200)
        self.assertEqual(h.result()['revision'],3)
        self.assertIn(USER['id'],call.call_args.args[1])
        self.assertEqual(call.call_args.kwargs['token'],'test-access')

    def test_missing_row_is_created_without_overwriting_a_concurrent_insert(self):
        with patch.object(S,'request',side_effect=[[],None,[{'data':DATA,'revision':0}]]) as call:
            row=S.load_row(USER['id'],'test-access')
        self.assertEqual(row['revision'],0)
        self.assertEqual(call.call_args_list[1].kwargs['prefer'],'resolution=ignore-duplicates')

    def test_expired_token_refreshes_and_sets_replacement_cookies(self):
        h=Handler(cookie='ds_access=expired; ds_refresh=test-refresh')
        with patch.object(S,'request',side_effect=[S.ProviderError(401),SESSION,USER,[{'data':DATA,'revision':0}]]):S.handle(h,'/api/data',accounts.valid_data)
        self.assertEqual(h.status,200)
        self.assertTrue(any(k=='Set-Cookie' and 'ds_access=test-access' in v for k,v in h.sent))

    def test_stale_revision_returns_conflict_and_never_overwrites_without_revision_filter(self):
        h=Handler('POST',{'data':DATA,'revision':3,'user_id':'someone-else'},cookie='ds_access=test-access')
        with patch.object(S,'request',side_effect=[USER,[]]) as call:S.handle(h,'/api/data',accounts.valid_data)
        self.assertEqual(h.status,409)
        self.assertIn('revision=eq.3',call.call_args.args[1])
        self.assertIn(USER['id'],call.call_args.args[1])
        self.assertNotIn('someone-else',call.call_args.args[1])

    def test_patch_success_advances_revision(self):
        h=Handler('POST',{'data':DATA,'revision':3},cookie='ds_access=test-access')
        with patch.object(S,'request',side_effect=[USER,[{'revision':4}]]) as call:S.handle(h,'/api/data',accounts.valid_data)
        self.assertEqual(h.result()['revision'],4)
        self.assertEqual(call.call_args.kwargs['body']['revision'],4)

    def test_outage_does_not_turn_account_into_guest_mode(self):
        h=Handler(cookie='ds_access=test-access')
        with patch.object(S,'request',side_effect=S.ProviderError(503)):S.handle(h,'/api/session',accounts.valid_data)
        self.assertEqual(h.status,503)
        self.assertIn('error',h.result())
        self.assertNotIn('email',h.result())

    def test_partial_configuration_fails_closed_instead_of_using_sqlite(self):
        with patch.dict('os.environ',{'SUPABASE_PUBLISHABLE_KEY':''}),patch.object(accounts,'connect') as connect:
            h=Handler();accounts.handle(h,'/api/session')
        self.assertEqual(h.status,503)
        connect.assert_not_called()

    def test_foreign_origin_is_rejected_before_provider_request(self):
        h=Handler('POST',origin='https://other.example.invalid')
        with patch.object(S,'request') as call:S.handle(h,'/api/login',accounts.valid_data)
        self.assertEqual(h.status,403)
        call.assert_not_called()

    def test_request_sends_publishable_apikey_and_user_bearer(self):
        response=io.BytesIO(b'[]')
        with patch.object(S,'urlopen',return_value=response) as call:
            S.request('GET','/rest/v1/training_logs',token='test-access')
        headers={k.lower():v for k,v in call.call_args.args[0].header_items()}
        self.assertEqual(headers['apikey'],ENV['SUPABASE_PUBLISHABLE_KEY'])
        self.assertEqual(headers['authorization'],'Bearer test-access')

if __name__=='__main__':unittest.main()
