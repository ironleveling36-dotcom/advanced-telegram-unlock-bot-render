import os, sqlite3, time
from flask import Flask, request
import telebot
from telebot import types

BOT_TOKEN=os.getenv('BOT_TOKEN','')
ADMIN_IDS={int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}
WEBHOOK_URL=os.getenv('WEBHOOK_URL','').rstrip('/')
PAYMENT_QR_URL=os.getenv('PAYMENT_QR_URL','')
PAYMENT_TEXT=os.getenv('PAYMENT_TEXT','Send payment and submit your UTR for admin verification.')
PORT=int(os.getenv('PORT','10000'))
if not BOT_TOKEN: raise RuntimeError('BOT_TOKEN is required')
bot=telebot.TeleBot(BOT_TOKEN,parse_mode='HTML'); app=Flask(__name__); DB='bot.db'

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init():
 c=db(); c.executescript('''CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY, username TEXT, invited_by INTEGER, referrals INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS links(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,url TEXT,required_ref INTEGER DEFAULT 2,enabled INTEGER DEFAULT 1); CREATE TABLE IF NOT EXISTS unlocks(uid INTEGER,link_id INTEGER,method TEXT,PRIMARY KEY(uid,link_id)); CREATE TABLE IF NOT EXISTS admins(uid INTEGER PRIMARY KEY); CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,uid INTEGER,link_id INTEGER,utr TEXT,status TEXT DEFAULT 'pending');''');
 for uid in ADMIN_IDS: c.execute('INSERT OR IGNORE INTO admins(uid) VALUES(?)',(uid,))
 c.commit(); c.close()
init()

def admin(uid):
 c=db(); x=c.execute('SELECT 1 FROM admins WHERE uid=?',(uid,)).fetchone(); c.close(); return bool(x)
def ensure(u,inv=None):
 c=db(); x=c.execute('SELECT uid FROM users WHERE uid=?',(u.id,)).fetchone()
 if not x:
  if inv==u.id: inv=None
  c.execute('INSERT INTO users(uid,username,invited_by) VALUES(?,?,?)',(u.id,u.username or '',inv))
  if inv: c.execute('UPDATE users SET referrals=referrals+1 WHERE uid=?',(inv,))
 c.commit(); c.close()
def unlocked(uid,lid):
 if admin(uid): return True
 c=db(); x=c.execute('SELECT 1 FROM unlocks WHERE uid=? AND link_id=?',(uid,lid)).fetchone(); c.close(); return bool(x)
def menu(uid):
 k=types.InlineKeyboardMarkup(row_width=1); c=db(); rows=c.execute('SELECT * FROM links WHERE enabled=1 ORDER BY id').fetchall(); c.close()
 for r in rows: k.add(types.InlineKeyboardButton(('🔓 ' if unlocked(uid,r['id']) else '🔒 ')+r['title'],callback_data=f'link:{r["id"]}'))
 k.add(types.InlineKeyboardButton('👥 Referrals',callback_data='refs'),types.InlineKeyboardButton('💳 Payment',callback_data='pay')); return k
def amenu():
 k=types.InlineKeyboardMarkup(row_width=2)
 for t,d in [('➕ Add Link','a:add'),('➖ Remove','a:remove'),('🎯 Referral Count','a:ref'),('👤 Grant User','a:grant'),('💳 Payments','a:payments'),('📊 Stats','a:stats')]: k.add(types.InlineKeyboardButton(t,callback_data=d))
 return k
def edit(m,text,k):
 try: bot.edit_message_text(text,m.chat.id,m.message_id,reply_markup=k)
 except: bot.send_message(m.chat.id,text,reply_markup=k)

@app.get('/')
def health(): return {'status':'ok','service':'advanced-unlock-bot'}
@app.get('/health')
def health2(): return 'OK',200
@app.post('/telegram/webhook')
def webhook(): bot.process_new_updates([telebot.types.Update.de_json(request.data.decode())]); return 'OK',200

@bot.message_handler(commands=['start'])
def start(m):
 inv=None; p=m.text.split(maxsplit=1)
 if len(p)==2 and p[1].startswith('ref_'):
  try: inv=int(p[1][4:])
  except: pass
 ensure(m.from_user,inv); bot.send_message(m.chat.id,'🌈 <b>WELCOME TO UNLOCK CENTER</b> 🌈\n\n🔗 Select a resource below.',reply_markup=menu(m.from_user.id))
@bot.message_handler(commands=['admin'])
def admincmd(m):
 if admin(m.from_user.id): bot.send_message(m.chat.id,'👑 <b>ADMIN CONTROL CENTER</b>',reply_markup=amenu())
 else: bot.reply_to(m,'⛔ Admin access only.')
@bot.message_handler(commands=['addlink'])
def addlink(m):
 if not admin(m.from_user.id): return
 try:
  title,url,ref=m.text[len('/addlink '):].split('|',2); c=db(); c.execute('INSERT INTO links(title,url,required_ref) VALUES(?,?,?)',(title.strip(),url.strip(),int(ref))); c.commit(); c.close(); bot.reply_to(m,'✅ Link added.')
 except: bot.reply_to(m,'Format: /addlink TITLE | URL | REFCOUNT')
@bot.message_handler(commands=['removelink'])
def removelink(m):
 if not admin(m.from_user.id): return
 try:
  lid=int(m.text.split()[1]); c=db(); c.execute('DELETE FROM links WHERE id=?',(lid,)); c.commit(); c.close(); bot.reply_to(m,'✅ Link removed.')
 except: bot.reply_to(m,'Format: /removelink ID')
@bot.message_handler(commands=['setref'])
def setref(m):
 if not admin(m.from_user.id): return
 try:
  lid,n=map(int,m.text.split()[1:3]); c=db(); c.execute('UPDATE links SET required_ref=? WHERE id=?',(n,lid)); c.commit(); c.close(); bot.reply_to(m,'🎯 Referral count updated.')
 except: bot.reply_to(m,'Format: /setref LINK_ID COUNT')
@bot.message_handler(commands=['grant'])
def grant(m):
 if not admin(m.from_user.id): return
 try:
  p=m.text.split(); uid=int(p[1]); c=db(); rows=c.execute('SELECT id FROM links').fetchall() if len(p)<3 or p[2].upper()=='ALL' else [ {'id':int(p[2])} ]
  for r in rows: c.execute('INSERT OR REPLACE INTO unlocks(uid,link_id,method) VALUES(?,?,?)',(uid,r['id'],'admin'))
  c.commit(); c.close(); bot.reply_to(m,'🔓 User fully unlocked by admin.')
 except: bot.reply_to(m,'Format: /grant USER_ID [LINK_ID|ALL]')
@bot.message_handler(commands=['utr'])
def utr(m):
 p=m.text.split();
 if len(p)<2: bot.reply_to(m,'Use /utr YOUR_UTR or /utr LINK_ID YOUR_UTR'); return
 lid=int(p[1]) if len(p)>2 and p[1].isdigit() else 1; value=p[2] if len(p)>2 else p[1]
 c=db(); c.execute('INSERT INTO payments(uid,link_id,utr) VALUES(?,?,?)',(m.from_user.id,lid,value)); c.commit(); c.close(); bot.reply_to(m,'🟡 <b>UTR submitted.</b> Awaiting admin verification.')

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
 bot.answer_callback_query(c.id); uid=c.from_user.id
 if c.data=='refs':
  cdb=db(); u=cdb.execute('SELECT referrals FROM users WHERE uid=?',(uid,)).fetchone(); cdb.close(); n=u['referrals'] if u else 0; me=bot.get_me(); ref=f'https://t.me/{me.username}?start=ref_{uid}'
  edit(c.message,f'👥 <b>Referral Center</b>\n\nVerified referrals: <b>{n}</b>\n\n<code>{ref}</code>',menu(uid)); return
 if c.data=='pay':
  t=f'💳 <b>PAYMENT UNLOCK</b>\n\n{PAYMENT_TEXT}\n'
  if PAYMENT_QR_URL: t+=f'\nQR: {PAYMENT_QR_URL}\n'
  t+='\nSubmit: <code>/utr YOUR_UTR</code>'; bot.send_message(uid,t); return
 if c.data=='back': edit(c.message,'🌈 <b>UNLOCK CENTER</b>',menu(uid)); return
 if c.data.startswith('link:'):
  lid=int(c.data.split(':')[1]); cdb=db(); r=cdb.execute('SELECT * FROM links WHERE id=? AND enabled=1',(lid,)).fetchone(); u=cdb.execute('SELECT referrals FROM users WHERE uid=?',(uid,)).fetchone(); cdb.close()
  if not r:return
  if unlocked(uid,lid):
   k=types.InlineKeyboardMarkup(); k.add(types.InlineKeyboardButton('🚀 OPEN RESOURCE',url=r['url']),types.InlineKeyboardButton('⬅️ Back',callback_data='back')); edit(c.message,f'🟢 <b>{r["title"]}</b>\n\nUnlocked.',k)
  else:
   n=u['referrals'] if u else 0; k=types.InlineKeyboardMarkup(); k.add(types.InlineKeyboardButton(f'👥 Refer ({r["required_ref"]})',callback_data='refs'),types.InlineKeyboardButton('💳 Pay & Unlock',callback_data='pay'),types.InlineKeyboardButton('🔄 Check',callback_data=f'link:{lid}')); edit(c.message,f'🔒 <b>{r["title"]}</b>\n\nRequired referrals: <b>{r["required_ref"]}</b>\nYour referrals: <b>{n}</b>',k)
  return
 if c.data.startswith('a:') and admin(uid):
  a=c.data[2:]
  if a=='stats':
   cdb=db(); u=cdb.execute('SELECT COUNT(*) n FROM users').fetchone()['n']; l=cdb.execute('SELECT COUNT(*) n FROM links').fetchone()['n']; p=cdb.execute("SELECT COUNT(*) n FROM payments WHERE status='pending'").fetchone()['n']; cdb.close(); bot.send_message(uid,f'📊 <b>Stats</b>\n\n👥 Users: {u}\n🔗 Links: {l}\n💳 Pending: {p}')
  elif a=='payments':
   cdb=db(); rows=cdb.execute("SELECT * FROM payments WHERE status='pending' ORDER BY id DESC LIMIT 10").fetchall(); cdb.close()
   if not rows: bot.send_message(uid,'✅ No pending payments.')
   for r in rows:
    k=types.InlineKeyboardMarkup(); k.add(types.InlineKeyboardButton('✅ Approve',callback_data=f'approve:{r["id"]}'),types.InlineKeyboardButton('❌ Reject',callback_data=f'reject:{r["id"]}')); bot.send_message(uid,f'💳 Payment #{r["id"]}\nUser: <code>{r["uid"]}</code>\nLink: {r["link_id"]}\nUTR: <code>{r["utr"]}</code>',reply_markup=k)
  else: bot.send_message(uid,'⚙️ Use /addlink, /removelink, /setref or /grant for this control.')
  return
 if c.data.startswith('approve:') or c.data.startswith('reject:'):
  if not admin(uid): return
  pid=int(c.data.split(':')[1]); status='approved' if c.data.startswith('approve') else 'rejected'; cdb=db(); p=cdb.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone()
  if p:
   cdb.execute('UPDATE payments SET status=? WHERE id=?',(status,pid))
   if status=='approved': cdb.execute('INSERT OR REPLACE INTO unlocks(uid,link_id,method) VALUES(?,?,?)',(p['uid'],p['link_id'],'payment'))
   cdb.commit()
  cdb.close(); bot.send_message(uid,('✅ Approved' if status=='approved' else '❌ Rejected')+f' payment #{pid}')
  if p: bot.send_message(p['uid'],'🎉 Payment approved and your resource is unlocked.' if status=='approved' else '❌ Payment rejected.')

if __name__=='__main__':
 import threading
 threading.Thread(target=lambda: app.run(host='0.0.0.0',port=PORT),daemon=True).start()
 if WEBHOOK_URL: bot.remove_webhook(); bot.set_webhook(WEBHOOK_URL+'/telegram/webhook')
 else: bot.remove_webhook()
 while True: time.sleep(3600)
