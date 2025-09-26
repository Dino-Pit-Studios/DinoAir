#!/usr/bin/env python3
"""
Setup script for GitHub Security Loader

This script sets up the environment and installs required dependencies.
"""

import os
import subprocess
import sys


def install_pygithub():
    """Install PyGithub library."""
    print("📦 Installing PyGithub...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "PyGithub"])
        print("✅ PyGithub installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install PyGithub: {e}")
        sys.exit(1)


def setup_environment():
    """Setup environment variables securely."""
    print("\n🔐 Environment Setup")
    print("=" * 50)

    # Check if token is already set
    if os.getenv("GITHUB_TOKEN"):
        print("✅ GITHUB_TOKEN already set in environment")
        return

    print("To set your GitHub token securely, run one of these commands:")
    print("\n📋 PowerShell:")
    print('$env:GITHUB_TOKEN="your_github_pat_here"')

    print("\n📋 Command Prompt:")
    print("set GITHUB_TOKEN=your_github_pat_here")

    print("\n📋 For permanent setup (PowerShell as Administrator):")
    print('[Environment]::SetEnvironmentVariable("GITHUB_TOKEN", "your_github_pat_here", "User")')

    print("\n⚠️  SECURITY NOTE:")
    print("- Never commit tokens to version control")
    print("- Use environment variables or secure credential stores")
    print("- Rotate tokens regularly")
    print("- Use minimal required scopes")


def create_gitignore_entry():
    """Ensure sensitive files are in .gitignore."""
    gitignore_path = ".gitignore"
    sensitive_patterns = [
        "# Security and credentials",
        "*.token",
        "*.key",
        ".env",
        ".env.*",
        "secrets.json",
        "*_security_issues.json",
        "github_token.txt",
    ]

    # Read existing .gitignore
    existing_content = ""
    if os.path.exists(gitignore_path):
        with open(gitignore_path, encoding="utf-8") as f:
            existing_content = f.read()

    # Add missing patterns
    new_patterns = []
    for pattern in sensitive_patterns:
        if pattern not in existing_content:
            new_patterns.append(pattern)

    if new_patterns:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(new_patterns) + "\n")
        print(f"✅ Added {len(new_patterns)} security patterns to .gitignore")
    else:
        print("✅ .gitignore already contains security patterns")


def main():
    """Main setup function."""
    print("🚀 GitHub Security Loader Setup")
    print("=" * 40)

    # Install dependencies
    install_pygithub()

    # Setup environment
    setup_environment()

    # Update .gitignore
    create_gitignore_entry()

    print("\n✅ Setup complete!")
    print("\nNext steps:")
    print("1. Set your GITHUB_TOKEN environment variable")
    print("2. Run: python simple_github_security.py")


if __name__ == "__main__":
    main()
