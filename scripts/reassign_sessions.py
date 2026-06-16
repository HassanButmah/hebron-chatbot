#!/usr/bin/env python3
"""
reassign_sessions.py  —  Make old sessions visible in the new widget
=====================================================================
Background
----------
The Streamlit widget ran inside a sandboxed <iframe> with a different
browser origin, so its localStorage was separate from the main page.
When you switched to the pure HTML/JS widget the 'rag_user_id' stored
in the main-page localStorage is a DIFFERENT value from the one used by
the old Streamlit sessions.  All your old conversations exist in the DB
but the widget can't find them because it queries by user_id.

What this script does
---------------------
It ONLY updates the user_id column on old chat_sessions rows — every
conversation stays completely intact (same session_id, same messages,
same timestamps).  Nothing is merged, nothing is deleted.

How to use (once per PC)
------------------------
1.  Open the chatbot widget in your browser on THIS PC and send one
    message.  This creates a fresh session under the new user_id.
2.  Run:   python reassign_sessions.py
    The script prints all sessions.  It auto-detects the new user_id
    from the newest session.
3.  Review the preview, then type  yes  to confirm.
4.  Refresh the widget — all old conversations should now appear.

Flags
-----
  --apply              Actually write changes (default is dry-run).
  --new-uid  <uid>     Override the auto-detected new user_id.
  --keep-test          Keep the test message/session you created in
                       step 1 (default: it is deleted after reassign
                       since it was only needed to identify the uid).
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from database import SessionLocal, ChatSession, ChatMessage


# ────────────────────────────────────────────────────────────────────────────

def _ts(dt):
    if dt is None:
        return "—"
    try:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt)


def load_sessions(db):
    sessions = (
        db.query(ChatSession)
        .order_by(ChatSession.start_time.desc())
        .all()
    )
    result = []
    for s in sessions:
        count = db.query(ChatMessage).filter(ChatMessage.session_id == s.session_id).count()
        last_msg = (
            db.query(ChatMessage.timestamp)
            .filter(ChatMessage.session_id == s.session_id)
            .order_by(ChatMessage.timestamp.desc())
            .first()
        )
        last_activity = last_msg[0] if last_msg else s.start_time
        result.append({
            "session": s,
            "msg_count": count,
            "last_activity": last_activity,
        })
    return result


def print_table(sessions_info):
    col_sid  = 38
    col_uid  = 36
    col_msgs = 6
    col_st   = 19
    col_last = 19

    header = (
        f"{'#':<4}"
        f"{'Session ID':<{col_sid}}"
        f"{'User ID':<{col_uid}}"
        f"{'Msgs':>{col_msgs}}"
        f"  {'Created':<{col_st}}"
        f"  {'Last message':<{col_last}}"
    )
    sep = "=" * len(header)
    print("\n" + sep)
    print(header)
    print("-" * len(header))
    for i, info in enumerate(sessions_info, 1):
        s = info["session"]
        print(
            f"{i:<4}"
            f"{str(s.session_id)[:col_sid-1]:<{col_sid}}"
            f"{str(s.user_id or '')[:col_uid-1]:<{col_uid}}"
            f"{info['msg_count']:>{col_msgs}}"
            f"  {_ts(s.start_time):<{col_st}}"
            f"  {_ts(info['last_activity']):<{col_last}}"
        )
    print(sep)


def run(new_uid_override: str | None, apply: bool, keep_test: bool):
    db = SessionLocal()
    try:
        sessions_info = load_sessions(db)

        if not sessions_info:
            print("\nNo sessions found in database.")
            return

        print_table(sessions_info)

        # ── Detect new user_id ───────────────────────────────────────────
        if new_uid_override:
            new_uid = new_uid_override.strip()
            anchor_info = next(
                (x for x in sessions_info if str(x["session"].user_id) == new_uid),
                None,
            )
            if anchor_info is None:
                print(f"\n✗  --new-uid '{new_uid}' not found in any session.")
                return
        else:
            # The newest session (top of list) is the test message just sent
            anchor_info = sessions_info[0]
            new_uid = str(anchor_info["session"].user_id or "")

        anchor_session = anchor_info["session"]

        print(
            f"\n→  New user_id (from newest session)  :  {new_uid}"
            f"\n   Anchor session ID                  :  {anchor_session.session_id}"
            f"\n   Anchor session created             :  {_ts(anchor_session.start_time)}"
        )

        if not new_uid:
            print("\n✗  The anchor session has no user_id — cannot proceed.")
            return

        # ── Sessions that need reassigning ───────────────────────────────
        to_reassign = [
            info for info in sessions_info
            if str(info["session"].user_id or "") != new_uid
        ]

        test_sessions = [
            info for info in sessions_info
            if str(info["session"].session_id) == str(anchor_session.session_id)
        ]

        print(f"\n   Sessions to reassign (old user_id)  :  {len(to_reassign)}")
        print(f"   Messages in those sessions          :  {sum(x['msg_count'] for x in to_reassign)}")
        print(f"   Sessions already on new user_id     :  {len(sessions_info) - len(to_reassign)}")

        if not to_reassign:
            print("\n✓  All sessions already use the new user_id — nothing to do.")
            return

        delete_test = (not keep_test) and anchor_info["msg_count"] <= 3
        if delete_test:
            print(
                f"\n   Test session ({anchor_session.session_id[:20]}...) "
                f"has {anchor_info['msg_count']} message(s) and will be DELETED after reassign."
                "\n   (Pass --keep-test to keep it.)"
            )

        if not apply:
            print(
                "\n[DRY RUN]  No changes made."
                "\nRun with  --apply  to execute.\n"
            )
            return

        confirm = input("\nType  yes  to reassign all old sessions to the new user_id: ").strip().lower()
        if confirm != "yes":
            print("Cancelled.")
            return

        # ── Reassign ─────────────────────────────────────────────────────
        for info in to_reassign:
            info["session"].user_id = new_uid

        db.flush()

        # ── Optionally remove the test session ───────────────────────────
        if delete_test:
            test_msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == str(anchor_session.session_id))
                .all()
            )
            for msg in test_msgs:
                db.delete(msg)
            db.delete(anchor_session)
            db.flush()
            print(f"\n✓  Deleted test session and its {len(test_msgs)} message(s).")

        db.commit()

        print(f"✓  Reassigned {len(to_reassign)} sessions → user_id  {new_uid}")
        print("\nDone.  Refresh the widget — all conversations should now appear in history.\n")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Reassign old sessions to the new widget user_id without merging them."
    )
    parser.add_argument("--apply",     action="store_true", help="Write changes to DB.")
    parser.add_argument("--new-uid",   metavar="UID",       help="Override auto-detected new user_id.")
    parser.add_argument("--keep-test", action="store_true", help="Keep the test session (don't delete it).")
    args = parser.parse_args()

    print(__doc__)
    run(new_uid_override=args.new_uid, apply=args.apply, keep_test=args.keep_test)


if __name__ == "__main__":
    main()
