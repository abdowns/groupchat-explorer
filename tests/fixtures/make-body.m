#import <Foundation/Foundation.h>
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSMutableAttributedString *text = [[NSMutableAttributedString alloc] initWithString:@"Café 👋 — an entirely fictional message."];
        [text addAttribute:@"__kIMMessagePartAttributeName" value:@0 range:NSMakeRange(0, text.length)];
        NSData *data = [NSArchiver archivedDataWithRootObject:text];
        return [data writeToFile:[NSString stringWithUTF8String:argv[1]] atomically:YES] ? 0 : 1;
    }
}
