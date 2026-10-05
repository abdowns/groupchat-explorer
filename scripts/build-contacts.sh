#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Darwin ]; then exit 0; fi
mkdir -p native/contacts/target
contacts_binary=native/contacts/target/gc-contacts
if [ ! -f "$contacts_binary" ] || [ native/contacts/main.m -nt "$contacts_binary" ] || [ native/contacts/Info.plist -nt "$contacts_binary" ]; then
  clang -fobjc-arc native/contacts/main.m -o "$contacts_binary" -framework Contacts -framework Foundation \
    -Wl,-sectcreate,__TEXT,__info_plist,"$PWD/native/contacts/Info.plist"
  codesign --force --sign - --identifier org.groupchatexplorer.contacts "$contacts_binary"
fi
