#import <Foundation/Foundation.h>
#import <Vision/Vision.h>

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 2) return 2;
        NSURL *url = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]]];
        VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc] init];
        request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
        request.usesLanguageCorrection = YES;
        VNImageRequestHandler *handler = [[VNImageRequestHandler alloc] initWithURL:url options:@{}];
        NSError *error = nil;
        if (![handler performRequests:@[request] error:&error]) {
            fprintf(stderr, "OCR failed: %s\n", error.localizedDescription.UTF8String);
            return 1;
        }
        NSMutableArray *lines = [NSMutableArray array];
        for (VNRecognizedTextObservation *observation in request.results) {
            VNRecognizedText *candidate = [observation topCandidates:1].firstObject;
            if (candidate) [lines addObject:candidate.string];
        }
        NSData *data = [NSJSONSerialization dataWithJSONObject:@{@"text": [lines componentsJoinedByString:@"\n"]} options:0 error:&error];
        [[NSFileHandle fileHandleWithStandardOutput] writeData:data];
    }
    return 0;
}
