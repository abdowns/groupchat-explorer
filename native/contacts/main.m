// SPDX-License-Identifier: GPL-3.0-only
#import <Contacts/Contacts.h>
#import <Foundation/Foundation.h>

static void emit(NSDictionary *value) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingSortedKeys error:nil];
    if (data) [[NSFileHandle fileHandleWithStandardOutput] writeData:data];
}

static NSString *addressKey(NSString *value) {
    NSString *trimmed = [[value stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet] lowercaseString];
    if ([trimmed containsString:@"@"]) return trimmed;
    NSRegularExpression *valid = [NSRegularExpression regularExpressionWithPattern:@"^[+0-9().\\s-]+$" options:0 error:nil];
    if (![valid numberOfMatchesInString:trimmed options:0 range:NSMakeRange(0, trimmed.length)]) return @"";
    NSRegularExpression *pattern = [NSRegularExpression regularExpressionWithPattern:@"[^0-9]" options:0 error:nil];
    NSString *digits = [pattern stringByReplacingMatchesInString:trimmed options:0 range:NSMakeRange(0, trimmed.length) withTemplate:@""];
    if ([trimmed hasPrefix:@"00"]) digits = [digits substringFromIndex:2];
    if (digits.length == 10 && ![trimmed hasPrefix:@"+"] && ![trimmed hasPrefix:@"00"]) digits = [@"1" stringByAppendingString:digits];
    return digits.length >= 7 ? digits : @"";
}

static NSDictionary *record(CNContact *contact, NSSet *wanted, BOOL isMe) {
    NSMutableSet *matched = [NSMutableSet set];
    for (CNLabeledValue<CNPhoneNumber *> *phone in contact.phoneNumbers) {
        NSString *key = addressKey(phone.value.stringValue);
        if ([wanted containsObject:key]) [matched addObject:key];
    }
    for (CNLabeledValue<NSString *> *email in contact.emailAddresses) {
        NSString *key = addressKey(email.value);
        if ([wanted containsObject:key]) [matched addObject:key];
    }
    if (!matched.count && !(isMe && [wanted containsObject:@"me"])) return nil;
    NSString *name = [CNContactFormatter stringFromContact:contact style:CNContactFormatterStyleFullName];
    if (!name.length) return nil;
    return @{@"id": contact.identifier, @"name": name, @"keys": [[matched allObjects] sortedArrayUsingSelector:@selector(compare:)], @"is_me": @(isMe)};
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc > 1 && strcmp(argv[1], "--self-test") == 0) {
            NSDictionary *cases = @{@"+1 (202) 555-0100": @"12025550100", @"202-555-0100": @"12025550100",
                @"0044 20 7946 0100": @"442079460100", @"0049 12345678": @"4912345678",
                @" Name@EXAMPLE.invalid ": @"name@example.invalid", @"member1234567": @""};
            for (NSString *input in cases) {
                if (![addressKey(input) isEqualToString:cases[input]]) return 1;
            }
            CNMutableContact *fixture = [CNMutableContact new];
            fixture.givenName = @"Zoë";
            fixture.familyName = @"Neighbor";
            fixture.phoneNumbers = @[[CNLabeledValue labeledValueWithLabel:CNLabelPhoneNumberMobile value:[CNPhoneNumber phoneNumberWithStringValue:@"202-555-0100"]]];
            NSDictionary *row = record(fixture, [NSSet setWithObject:@"12025550100"], NO);
            if (![row[@"name"] isEqualToString:@"Zoë Neighbor"] || [row[@"keys"] count] != 1) return 2;
            if (record(fixture, [NSSet setWithObject:@"12025550199"], NO) != nil) return 3;
            puts("ok");
            return 0;
        }
        NSData *input = [[NSFileHandle fileHandleWithStandardInput] readDataToEndOfFile];
        NSDictionary *options = [NSJSONSerialization JSONObjectWithData:input options:0 error:nil] ?: @{};
        NSSet *wanted = [NSSet setWithArray:options[@"keys"] ?: @[]];
        CNContactStore *store = [CNContactStore new];
        CNAuthorizationStatus status = [CNContactStore authorizationStatusForEntityType:CNEntityTypeContacts];
        if (status == CNAuthorizationStatusNotDetermined && [options[@"request_access"] boolValue]) {
            __block BOOL finished = NO;
            [store requestAccessForEntityType:CNEntityTypeContacts completionHandler:^(BOOL granted, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{ finished = YES; });
            }];
            while (!finished) [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
            status = [CNContactStore authorizationStatusForEntityType:CNEntityTypeContacts];
        }
        if (status == CNAuthorizationStatusNotDetermined || status == CNAuthorizationStatusDenied || status == CNAuthorizationStatusRestricted) {
            emit(@{@"status": status == CNAuthorizationStatusNotDetermined ? @"not_requested" : @"denied", @"contacts": @[]});
            return 0;
        }
        NSArray *keys = @[[CNContactFormatter descriptorForRequiredKeysForStyle:CNContactFormatterStyleFullName], CNContactPhoneNumbersKey, CNContactEmailAddressesKey];
        NSMutableArray *rows = [NSMutableArray array];
        CNContactFetchRequest *request = [[CNContactFetchRequest alloc] initWithKeysToFetch:keys];
        request.unifyResults = YES;
        NSError *error = nil;
        BOOL success = [store enumerateContactsWithFetchRequest:request error:&error usingBlock:^(CNContact *contact, BOOL *stop) {
            NSDictionary *row = record(contact, wanted, NO);
            if (row) [rows addObject:row];
        }];
        if (success) {
            if ([wanted containsObject:@"me"]) {
                CNContact *me = [store unifiedMeContactWithKeysToFetch:keys error:nil];
                if (me) {
                    NSDictionary *row = record(me, wanted, YES);
                    if (row) [rows addObject:row];
                }
            }
            emit(@{@"status": @"available", @"contacts": rows});
        } else {
            emit(@{@"status": @"error", @"contacts": @[], @"error": @"Unable to read macOS Contacts. Check Contacts access in System Settings → Privacy & Security."});
        }
    }
    return 0;
}
