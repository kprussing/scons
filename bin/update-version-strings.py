#!/usr/bin/env python
#
# MIT License
#
# Copyright The SCons Foundation
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os
import sys
import argparse
import re

NEXT_PLACEHOLDER = 'NEXT_RELEASE'
PREV_PLACEHOLDER = 'PREVIOUS_RELEASE'

SKIP_DIRS = ('__pycache__', 'node_modules', 'template', 'build')


def update_file(file_path, next_version, prev_version, dry_run=False):
    """Replace release placeholders in a single file.

    Returns a (found, modified) tuple of ints so callers can accumulate counts.
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except (IOError, OSError):
        return 0, 0

    updated = re.sub(rf'\b{NEXT_PLACEHOLDER}\b', next_version, content)
    updated = re.sub(rf'\b{PREV_PLACEHOLDER}\b', prev_version, updated)

    if updated == content:
        return 0, 0

    if dry_run:
        print(f"Would update: {file_path}")
        return 1, 1

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(updated)
    except (IOError, OSError) as e:
        print(f"Failed to write {file_path}: {e}", file=sys.stderr)
        return 1, 0

    print(f"Updated: {file_path}")
    return 1, 1


def find_and_replace_version_strings(root_path, next_version, prev_version, dry_run=False):
    """Recursively replace release placeholders under *root_path*."""
    files_modified = 0
    files_found = 0

    for root, dirs, files in os.walk(root_path):
        # Skip hidden directories and common non-source directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_DIRS]

        for file in files:
            found, modified = update_file(
                os.path.join(root, file),
                next_version=next_version,
                prev_version=prev_version,
                dry_run=dry_run,
            )
            files_found += found
            files_modified += modified

    return files_found, files_modified


def main():
    parser = argparse.ArgumentParser(
        description=f"Search for and replace {NEXT_PLACEHOLDER} and {PREV_PLACEHOLDER} placeholders in files."
    )
    parser.add_argument(
        "path",
        nargs='?',
        default='.',
        help="Directory or file to search (default: current directory)"
    )
    parser.add_argument(
        "--next",
        dest="next_version",
        required=True,
        help=f"Version string to replace {NEXT_PLACEHOLDER} with"
    )
    parser.add_argument(
        "--prev",
        dest="prev_version",
        required=True,
        help=f"Version string to replace {PREV_PLACEHOLDER} with"
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Report what would change without writing any files"
    )

    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"Error: Path not found: {args.path}", file=sys.stderr)
        sys.exit(1)

    if os.path.isfile(args.path):
        files_found, files_modified = update_file(
            args.path,
            next_version=args.next_version,
            prev_version=args.prev_version,
            dry_run=args.dry_run,
        )
    else:
        files_found, files_modified = find_and_replace_version_strings(
            args.path,
            next_version=args.next_version,
            prev_version=args.prev_version,
            dry_run=args.dry_run,
        )

    verb = "would modify" if args.dry_run else "modified"
    print(f"\nSummary: Found {files_found} file(s), {verb} {files_modified} file(s)")


if __name__ == "__main__":
    main()
