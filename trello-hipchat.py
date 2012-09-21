#!/usr/bin/env python
# This is free and unencumbered software released into the public domain.

# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.

# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# For more information, please refer to <http://unlicense.org/>
import sys
import os
import re
import json
import urllib2, urllib
import fnmatch
import cgi

DEBUG = False
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))

try:
    execfile(ROOT_DIR + "/trello-hipchat.cfg")
except IOError:
    print "trello-hipchat.cfg not found"
    sys.exit(1)

try:
    PREV_ID = long(open(ROOT_DIR + "/last-action.id").read(), 16)
except IOError:
    PREV_ID = 0
LAST_ID = 0

ESC = cgi.escape

def trello(path, **kwargs):
    kwargs["key"] = TRELLO_API_KEY
    if "TRELLO_TOKEN" in globals():
        kwargs["token"] = TRELLO_TOKEN
    
    url = "https://api.trello.com/1" + path + "?" + urllib.urlencode(kwargs)
    if DEBUG and 0:
        print url
    req = urllib2.urlopen(url)
    data = req.read()
    return json.loads(data)

def msg(room_id, m, mtype="html"):
    if DEBUG:
        print m.encode("utf-8")
        return 

    data = {
        "from": "Trello",
        "message": m.encode("utf-8"),
        "message_format": mtype,
        "color": "purple",
        "room_id": room_id
    }
    
    data = urllib.urlencode(data)
    req = urllib2.urlopen("https://api.hipchat.com/v1/rooms/message?format=json&auth_token=%s" % HIPCHAT_API_KEY, data)
    req.read()
        
def trunc(s, maxlen=200):
    if len(s) >= maxlen:
        s = s[:maxlen] + "[...]"
    return s

def card_in_lists(n, list_names):
    for filt in list_names:
        if n == filt or fnmatch.fnmatch(n, filt):
            return True
    return False

rx_points = re.compile(r"^\(\d+\) (.*)$")
def card_name_strip(n):
    """Strip story-points embedded in card name"""
    m = rx_points.match(n)
    if m:
        return m.group(1)
    return n
    
def notify(board_id, list_names, room_id):
    global LAST_ID

    actions = trello("/boards/%s/actions" % board_id)
    if not actions:
        return
    for A in reversed(actions):
        if long(A["id"], 16) <= PREV_ID and not DEBUG:
            continue
        if A["type"] == "commentCard":
            card_id_short = A["data"]["card"]["idShort"]
            card_id = A["data"]["card"]["id"]
            card_url = "https://trello.com/card/%s/%s/%s" % (card_id, board_id, card_id_short)
            card_name = ESC(card_name_strip(A["data"]["card"]["name"]))
            list_name = trello("/cards/%s/list" % card_id)["name"]
            author = ESC(A["memberCreator"]["fullName"])
            if not card_in_lists(list_name, list_names):
                continue

            text = trunc(" ".join(A["data"]["text"].split()))            
            msg(room_id, "%s commented on card <a href=\"%s\">%s</a>: %s" % (author, card_url, card_name, text))

        elif A["type"] == "addAttachmentToCard":
            card_id_short = A["data"]["card"]["idShort"]
            card_id = A["data"]["card"]["id"]
            card_url = "https://trello.com/card/%s/%s/%s" % (card_id, board_id, card_id_short)
            card_name = ESC(card_name_strip(A["data"]["card"]["name"]))
            list_name = trello("/cards/%s/list" % card_id)["name"]
            author = ESC(A["memberCreator"]["fullName"])
            if not card_in_lists(list_name, list_names):
                continue        
            
            aname = ESC(A["data"]["attachment"]["name"])
            aurl = A["data"]["attachment"]["url"]
                    
            m = "%s added an attachment to card <a href=\"%s\">%s</a>: <a href=\"%s\">%s</a>" % (author, card_url, card_name, aurl, aname)
            msg(room_id, m)
            if aurl.lower().endswith("png") or aurl.lower().endswith("gif") or aurl.lower().endswith("jpg") or aurl.lower().endswith("jpeg"):
                msg(room_id, aurl, mtype="text")

        elif A["type"] == "updateCard":
            card_id_short = A["data"]["card"]["idShort"]
            card_id = A["data"]["card"]["id"]
            card_url = "https://trello.com/card/%s/%s/%s" % (card_id, board_id, card_id_short)
            card_name = ESC(card_name_strip(A["data"]["card"]["name"]))
            author = ESC(A["memberCreator"]["fullName"])

            if "idList" in A["data"]["old"] and \
               "idList" in A["data"]["card"]:
                # Move between lists
                old_list_id = A["data"]["old"]["idList"]
                new_list_id = A["data"]["card"]["idList"]
                n1 = trello("/list/%s" % old_list_id)["name"]
                n2 = trello("/list/%s" % new_list_id)["name"]

                if not card_in_lists(n1, list_names) and not card_in_lists(n2, list_names):
                    continue

                n1 = ESC(n1)
                n2 = ESC(n2)

                msg(room_id, "%s moved card <a href=\"%s\">%s</a> from list \"%s\" to list \"%s\"" % (
                    author, card_url, card_name, n1, n2))

        elif A["type"] == "updateCheckItemStateOnCard":
            card_id_short = A["data"]["card"]["idShort"]
            card_id = A["data"]["card"]["id"]
            card_url = "https://trello.com/card/%s/%s/%s" % (card_id, board_id, card_id_short)
            card_name = ESC(card_name_strip(A["data"]["card"]["name"]))
            list_name = trello("/cards/%s/list" % card_id)["name"]
            author = ESC(A["memberCreator"]["fullName"])
            if not card_in_lists(list_name, list_names):
                continue        

            if A["data"]["checkItem"]["state"] == "complete":
                msg(room_id, "%s completed checklist item \"%s\" in card <a href=\"%s\">%s</a>" %
                    (author, ESC(A["data"]["checkItem"]["name"]), card_url, card_name))

    LAST_ID = max(LAST_ID, long(A["id"], 16))


if __name__ == "__main__":
    for m in MONITOR:
        notify(m[0], **m[1])
    open(ROOT_DIR + "/last-action.id", "w").write(hex(LAST_ID))
