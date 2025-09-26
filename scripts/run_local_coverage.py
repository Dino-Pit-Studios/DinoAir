#!/usr/bin/env python3
"""
Local Coverage Runner

Run tests with coverage locally and generate reports.
"""

import subprocess
import sys
from pathlib import Path


def main():
    """Run coverage locally."""
    print("🧪 Running tests with coverage...")

    # Ensure we're in the project root
    project_root = Path(__file__).parent
    print(f"📂 Project root: {project_root}")

    try:
        # Run tests with coverage using pytest configuration
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-v",
        ]

        print(f"🚀 Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=project_root, check=False)

        if result.returncode == 0:
            print("✅ Tests completed successfully")
        else:
            print("⚠️  Some tests failed or no tests found")

        # Check if coverage file was created
        coverage_xml = project_root / "coverage.xml"
        coverage_html = project_root / "htmlcov" / "index.html"

        if coverage_xml.exists():
            print(f"✅ Coverage XML report generated: {coverage_xml}")

            # Show some basic coverage info
            try:
                # Security fix: Use defusedxml instead of xml.etree.ElementTree
                # to prevent XML External Entity (XXE) attacks
                try:
                    from defusedxml import ElementTree as ET
                except ImportError:
                    print("⚠️  Warning: defusedxml not installed. Using xml.etree with caution.")
                    print("   Install defusedxml for secure XML parsing: pip install defusedxml")
                    import xml.etree.ElementTree as ET

                tree = ET.parse(coverage_xml)
                root = tree.getroot()
                line_rate = root.get("line-rate", "unknown")
                branch_rate = root.get("branch-rate", "unknown")
                print(f"📊 Line coverage: {float(line_rate) * 100:.1f}%")
                print(f"📊 Branch coverage: {float(branch_rate) * 100:.1f}%")
            except Exception as e:
                print(f"⚠️  Could not parse coverage data: {e}")
        else:
            print("❌ No coverage XML report generated")

        if coverage_html.exists():
            print(f"📊 HTML report available: {coverage_html}")
        else:
            print("❌ No HTML coverage report generated")

        return result.returncode

    except FileNotFoundError:
        print("❌ pytest not found. Installing...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pytest", "pytest-cov"], check=False
        )
        return main()


if __name__ == "__main__":
    sys.exit(main())
