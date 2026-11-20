#!/usr/bin/env python3
"""VisionGuard User Profile / Account Creation Tool.

Usage:
    python scripts/create_user.py --email user@example.com --password mysecretpass --name "Jane Doe"
    python scripts/create_user.py --interactive
"""

import sys
import os
import argparse
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.db.mongodb import MongoDBClient, UserRepository
from app.auth.service import hash_password


def create_user_account(
    email: str,
    password: str,
    name: str = None,
):
    print("=" * 60)
    print("VisionGuard - User Account Creation")
    print("=" * 60)

    client = MongoDBClient.get_instance()
    if not client.connect():
        print("[ERROR] Could not connect to MongoDB. Is MongoDB running?")
        sys.exit(1)

    user_repo = UserRepository(client)

    # Check if user already exists
    existing = user_repo.get_by_email(email)
    if existing:
        print(f"[WARN] User with email '{email}' already exists (User ID: {existing.get('id')}).")
        return existing

    print("Hashing password (bcrypt 12 rounds)...")
    hashed = hash_password(password)

    display_name = name or email.split("@")[0].capitalize()

    print("Creating user record in MongoDB collection 'users'...")
    try:
        user_record = user_repo.create_user(
            email=email,
            password_hash=hashed,
            display_name=display_name,
        )
        print("\n[SUCCESS] User profile created successfully!")
        print(f"  User ID:       {user_record.get('id')}")
        print(f"  Email:         {user_record.get('email')}")
        print(f"  Display Name:  {user_record.get('display_name')}")
        print(f"  Status:        {user_record.get('status')}")
        print(f"  Created At:    {user_record.get('created_at')}")
        print("\nYou can now sign in with these credentials in the VisionGuard dashboard.")
        return user_record
    except Exception as e:
        print(f"[ERROR] Failed to create user: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Create a VisionGuard User Profile / Account")
    parser.add_argument("--email", "-e", type=str, help="User email address")
    parser.add_argument("--password", "-p", type=str, help="Password (minimum 6 characters)")
    parser.add_argument("--name", "-n", type=str, help="Display / Full Name")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive prompt mode")

    args = parser.parse_args()

    if args.interactive or not args.email or not args.password:
        print("\n--- VisionGuard Interactive User Profile Setup ---")
        email = input("Enter email address: ").strip() if not args.email else args.email
        password = input("Enter password (min 6 characters): ").strip() if not args.password else args.password
        name = input("Enter display name (optional): ").strip() if not args.name else args.name
    else:
        email = args.email
        password = args.password
        name = args.name

    if not email or "@" not in email:
        print("[ERROR] A valid email address is required.")
        sys.exit(1)
    if not password or len(password) < 6:
        print("[ERROR] Password must be at least 6 characters.")
        sys.exit(1)

    create_user_account(
        email=email,
        password=password,
        name=name if name else None,
    )


if __name__ == "__main__":
    main()
