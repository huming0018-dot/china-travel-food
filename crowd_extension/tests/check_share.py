"""The owner's offline share page contains only public invitation material."""
import base64
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'cloud'))
from crowd_share import write_share

invitation={'link':'https://crowd.example.test/crowd#invite='+'a'*64,
 'qr':'data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode(),
 'expires_at':'2026-10-13T12:00:00Z','operator_key':'SERVER_SECRET_MUST_NOT_LEAK'}
with tempfile.TemporaryDirectory() as temporary:
 root=Path(temporary);page=write_share(invitation,root,['android','windows'])
 content=page.read_text();assert invitation['link'] in content;assert '复制整条短信' in content
 assert invitation['operator_key'] not in content;assert 'SMS_URL' not in content;assert 'EXPIRY' not in content
 assert 'Windows' in content and '安卓' in content;assert '二维码' in content
 assert '可随时停止' in (root/'invite-sms.txt').read_text()
 for bad in ['http://crowd.example.test/crowd#invite='+'a'*64,'https://crowd.example.test/crowd?operator=secret#invite='+'a'*64]:
  rejected=root/'rejected'
  try: write_share({**invitation,'link':bad},rejected,['android']);raise AssertionError('invalid link accepted')
  except ValueError: pass
  assert not rejected.exists()
print('PASS share export: one SMS/QR, available devices, no operator credentials, malformed material rejected')
