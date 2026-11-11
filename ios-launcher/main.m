// chimiPack iOS launcher.
//
// Built WITHOUT the Apple SDK: the few runtime functions and methods used are declared here, every
// UIKit/WebKit class is looked up at runtime, and linking uses tiny hand-written .tbd stubs.
// Cross-compiled on Windows with LLVM (see build_ios_launcher.py). One binary serves every app:
// per-app settings come from Info.plist (ChimiEntry, ChimiFullscreen) and the web files from www/.

typedef _Bool BOOL;  // arm64 iOS uses a real bool
#define YES ((BOOL)1)
#define NO ((BOOL)0)
#define nil ((id)0)
typedef long NSInteger;
typedef unsigned long NSUInteger;
typedef double CGFloat;
typedef struct { CGFloat x, y; } CGPoint;
typedef struct { CGFloat width, height; } CGSize;
typedef struct { CGPoint origin; CGSize size; } CGRect;
typedef struct { NSUInteger location, length; } NSRange;
typedef void (*IMP)(void);

// --- Objective-C runtime + libc (declared by hand) -------------------------------------------
id objc_getClass(const char *name);
Class objc_allocateClassPair(Class superclass, const char *name, unsigned long extraBytes);
void objc_registerClassPair(Class cls);
BOOL class_addMethod(Class cls, SEL name, IMP imp, const char *types);
SEL sel_registerName(const char *name);
int strcmp(const char *a, const char *b);
int sscanf(const char *s, const char *fmt, ...);
int UIApplicationMain(int argc, char *argv[], id principalClassName, id delegateClassName);

#define CLS(n) objc_getClass(n)

__attribute__((objc_root_class))
@interface NSObject { Class isa; }
+ (id)alloc;
+ (id)new;
- (id)init;
- (id)retain;
- (void)release;
- (id)autorelease;
- (BOOL)respondsToSelector:(SEL)sel;
@end

// Method signatures for the dynamically looked-up classes (declaration only).
@interface NSObject (ChimiDeclarations)
+ (id)mainBundle;
- (id)infoDictionary;
- (id)objectForKey:(id)key;
- (id)resourcePath;
- (BOOL)boolValue;
+ (id)mainScreen;
- (CGRect)bounds;
- (id)initWithFrame:(CGRect)frame;
- (id)initWithFrame:(CGRect)frame configuration:(id)config;
- (void)setURLSchemeHandler:(id)handler forURLScheme:(id)scheme;
- (void)setAllowsInlineMediaPlayback:(BOOL)b;
- (void)setMediaTypesRequiringUserActionForPlayback:(NSUInteger)t;
- (id)preferences;
- (void)setJavaScriptCanOpenWindowsAutomatically:(BOOL)b;
- (id)scrollView;
- (void)setContentInsetAdjustmentBehavior:(NSInteger)b;
- (void)setBounces:(BOOL)b;
- (void)setAutoresizingMask:(NSUInteger)m;
- (void)setUIDelegate:(id)d;
- (void)setNavigationDelegate:(id)d;
- (void)setInspectable:(BOOL)b;
- (void)setView:(id)v;
- (void)setRootViewController:(id)vc;
- (id)rootViewController;
- (void)makeKeyAndVisible;
- (void)setBackgroundColor:(id)c;
+ (id)blackColor;
+ (id)URLWithString:(id)s;
+ (id)requestWithURL:(id)url;
- (id)loadRequest:(id)req;
- (id)stringByAppendingString:(id)s;
- (id)stringByAppendingPathComponent:(id)s;
- (id)stringByStandardizingPath;
- (id)stringByAddingPercentEncodingWithAllowedCharacters:(id)set;
+ (id)URLPathAllowedCharacterSet;
- (NSUInteger)length;
- (BOOL)isEqualToString:(id)s;
- (BOOL)hasPrefix:(id)s;
- (BOOL)hasSuffix:(id)s;
- (id)pathExtension;
- (id)lowercaseString;
- (const char *)UTF8String;
+ (id)stringWithUTF8String:(const char *)s;
+ (id)stringWithFormat:(id)fmt, ...;
- (id)request;
- (id)URL;
- (id)path;
- (id)scheme;
- (id)valueForHTTPHeaderField:(id)f;
+ (id)dataWithContentsOfFile:(id)path;
+ (id)data;
- (id)subdataWithRange:(NSRange)r;
+ (id)dictionaryWithObjectsAndKeys:(id)first, ...;
+ (id)dictionary;
- (id)initWithURL:(id)url statusCode:(NSInteger)code HTTPVersion:(id)v headerFields:(id)h;
- (void)didReceiveResponse:(id)r;
- (void)didReceiveData:(id)d;
- (void)didFinish;
- (id)targetFrame;
- (BOOL)isMainFrame;
+ (id)sharedApplication;
- (void)openURL:(id)url options:(id)opts completionHandler:(id)handler;
+ (id)alertControllerWithTitle:(id)t message:(id)m preferredStyle:(NSInteger)s;
+ (id)actionWithTitle:(id)t style:(NSInteger)s handler:(void (^)(id))h;
- (void)addAction:(id)a;
- (void)addTextFieldWithConfigurationHandler:(void (^)(id))h;
- (id)textFields;
- (id)firstObject;
- (id)text;
- (void)setText:(id)t;
- (void)presentViewController:(id)vc animated:(BOOL)a completion:(id)c;
- (id)presentedViewController;
@end

static id gEntry;
static id gWindow;

static id S(const char *s) { return [CLS("NSString") stringWithUTF8String:s]; }

static id mimeFor(id path) {
    const char *e = [[[path pathExtension] lowercaseString] UTF8String];
    static const char *map[][2] = {
        {"html", "text/html; charset=utf-8"}, {"htm", "text/html; charset=utf-8"},
        {"js", "text/javascript; charset=utf-8"}, {"mjs", "text/javascript; charset=utf-8"},
        {"css", "text/css; charset=utf-8"}, {"json", "application/json"}, {"map", "application/json"},
        {"txt", "text/plain; charset=utf-8"}, {"xml", "application/xml"}, {"svg", "image/svg+xml"},
        {"png", "image/png"}, {"jpg", "image/jpeg"}, {"jpeg", "image/jpeg"}, {"gif", "image/gif"},
        {"webp", "image/webp"}, {"ico", "image/x-icon"}, {"bmp", "image/bmp"}, {"wasm", "application/wasm"},
        {"mp3", "audio/mpeg"}, {"ogg", "audio/ogg"}, {"wav", "audio/wav"}, {"m4a", "audio/mp4"},
        {"mp4", "video/mp4"}, {"webm", "video/webm"}, {"woff", "font/woff"}, {"woff2", "font/woff2"},
        {"ttf", "font/ttf"}, {"otf", "font/otf"},
    };
    for (unsigned long i = 0; i < sizeof(map) / sizeof(map[0]); i++)
        if (e && strcmp(e, map[i][0]) == 0) return S(map[i][1]);
    return @"application/octet-stream";
}

static void present(id alert) {
    id vc = [gWindow rootViewController];
    while ([vc presentedViewController]) vc = [vc presentedViewController];
    [vc presentViewController:alert animated:YES completion:nil];
}

// Serves app://local/<path> from the bundle's www folder (with Range support for media).
@interface ChimiSchemeHandler : NSObject
@end
@implementation ChimiSchemeHandler
- (void)webView:(id)webView startURLSchemeTask:(id)task {
    id url = [[task request] URL];
    id path = [url path];
    if (!path || [path length] == 0 || [path isEqualToString:@"/"]) path = [@"/" stringByAppendingString:gEntry];
    if ([path hasSuffix:@"/"]) path = [path stringByAppendingString:@"index.html"];
    id www = [[[CLS("NSBundle") mainBundle] resourcePath] stringByAppendingPathComponent:@"www"];
    id file = [[www stringByAppendingString:path] stringByStandardizingPath];
    id data = nil;
    if ([file hasPrefix:[www stringByAppendingString:@"/"]]) data = [CLS("NSData") dataWithContentsOfFile:file];
    NSInteger status = data ? 200 : 404;
    if (!data) data = [CLS("NSData") data];
    NSUInteger total = [data length];
    id contentRange = nil;
    id range = [[task request] valueForHTTPHeaderField:@"Range"];
    if (status == 200 && range && total > 0) {
        unsigned long a = 0, b = total - 1;
        const char *r = [range UTF8String];
        int n = sscanf(r, "bytes=%lu-%lu", &a, &b);
        if (n >= 1 && a < total) {
            if (b >= total) b = total - 1;
            if (b >= a) {
                data = [data subdataWithRange:(NSRange){a, b - a + 1}];
                contentRange = [CLS("NSString") stringWithFormat:@"bytes %lu-%lu/%lu", a, b, (unsigned long)total];
                status = 206;
            }
        }
    }
    id len = [CLS("NSString") stringWithFormat:@"%lu", (unsigned long)[data length]];
    id headers = contentRange
        ? [CLS("NSDictionary") dictionaryWithObjectsAndKeys:mimeFor(path), @"Content-Type", len, @"Content-Length",
              @"bytes", @"Accept-Ranges", @"no-cache", @"Cache-Control", contentRange, @"Content-Range", nil]
        : [CLS("NSDictionary") dictionaryWithObjectsAndKeys:mimeFor(path), @"Content-Type", len, @"Content-Length",
              @"bytes", @"Accept-Ranges", @"no-cache", @"Cache-Control", nil];
    id resp = [[[CLS("NSHTTPURLResponse") alloc] initWithURL:url statusCode:status HTTPVersion:@"HTTP/1.1"
                                                 headerFields:headers] autorelease];
    [task didReceiveResponse:resp];
    [task didReceiveData:data];
    [task didFinish];
}
- (void)webView:(id)webView stopURLSchemeTask:(id)task {
}
@end

static BOOL returnYes(id self, SEL _cmd) { return YES; }

@interface ChimiAppDelegate : NSObject
@end
@implementation ChimiAppDelegate
- (id)window { return gWindow; }
- (void)setWindow:(id)w { gWindow = w; }

- (BOOL)application:(id)app didFinishLaunchingWithOptions:(id)options {
    id info = [[CLS("NSBundle") mainBundle] infoDictionary];
    gEntry = [info objectForKey:@"ChimiEntry"];
    if (!gEntry) gEntry = @"index.html";
    BOOL fullscreen = [[info objectForKey:@"ChimiFullscreen"] boolValue];

    // A view controller class that can hide the status bar and home indicator.
    Class vcClass = (Class)CLS("ChimiViewController");
    if (!vcClass) {
        vcClass = objc_allocateClassPair((Class)CLS("UIViewController"), "ChimiViewController", 0);
        if (fullscreen) {
            class_addMethod(vcClass, sel_registerName("prefersStatusBarHidden"), (IMP)returnYes, "B@:");
            class_addMethod(vcClass, sel_registerName("prefersHomeIndicatorAutoHidden"), (IMP)returnYes, "B@:");
        }
        objc_registerClassPair(vcClass);
    }

    CGRect frame = [[CLS("UIScreen") mainScreen] bounds];
    gWindow = [[CLS("UIWindow") alloc] initWithFrame:frame];
    [gWindow setBackgroundColor:[CLS("UIColor") blackColor]];

    id config = [[CLS("WKWebViewConfiguration") alloc] init];
    [config setURLSchemeHandler:[[ChimiSchemeHandler alloc] init] forURLScheme:@"app"];
    [config setAllowsInlineMediaPlayback:YES];
    [config setMediaTypesRequiringUserActionForPlayback:0];
    [[config preferences] setJavaScriptCanOpenWindowsAutomatically:YES];

    id web = [[CLS("WKWebView") alloc] initWithFrame:frame configuration:config];
    [[web scrollView] setContentInsetAdjustmentBehavior:2];  // never: page controls the safe area
    [[web scrollView] setBounces:NO];
    [web setAutoresizingMask:18];                              // flexible width + height
    [web setUIDelegate:self];
    [web setNavigationDelegate:self];
    if ([web respondsToSelector:@selector(setInspectable:)]) [web setInspectable:YES];

    id vc = [[(id)vcClass alloc] init];
    [vc setView:web];
    [gWindow setRootViewController:vc];
    [gWindow makeKeyAndVisible];

    id encoded = [gEntry stringByAddingPercentEncodingWithAllowedCharacters:[CLS("NSCharacterSet") URLPathAllowedCharacterSet]];
    id url = [CLS("NSURL") URLWithString:[@"app://local/" stringByAppendingString:encoded]];
    [web loadRequest:[CLS("NSURLRequest") requestWithURL:url]];
    return YES;
}

// Links to other websites open in Safari; everything inside the app stays here.
- (void)webView:(id)webView decidePolicyForNavigationAction:(id)action decisionHandler:(void (^)(NSInteger))handler {
    id url = [[action request] URL];
    id scheme = [url scheme];
    id target = [action targetFrame];
    if (!scheme || [scheme isEqualToString:@"app"] || [scheme isEqualToString:@"about"] ||
        [scheme isEqualToString:@"blob"] || [scheme isEqualToString:@"data"] || (target && ![target isMainFrame])) {
        handler(1);  // allow
        return;
    }
    [[CLS("UIApplication") sharedApplication] openURL:url options:[CLS("NSDictionary") dictionary] completionHandler:nil];
    handler(0);  // cancel
}

// window.open / target=_blank
- (id)webView:(id)webView createWebViewWithConfiguration:(id)config forNavigationAction:(id)action windowFeatures:(id)features {
    id url = [[action request] URL];
    if ([[url scheme] isEqualToString:@"app"]) [webView loadRequest:[action request]];
    else if (url) [[CLS("UIApplication") sharedApplication] openURL:url options:[CLS("NSDictionary") dictionary] completionHandler:nil];
    return nil;
}

// alert(), confirm() and prompt() would otherwise silently do nothing in WKWebView.
- (void)webView:(id)webView runJavaScriptAlertPanelWithMessage:(id)message initiatedByFrame:(id)frame completionHandler:(void (^)(void))done {
    id alert = [CLS("UIAlertController") alertControllerWithTitle:nil message:message preferredStyle:1];
    [alert addAction:[CLS("UIAlertAction") actionWithTitle:@"OK" style:0 handler:^(id a) { done(); }]];
    present(alert);
}
- (void)webView:(id)webView runJavaScriptConfirmPanelWithMessage:(id)message initiatedByFrame:(id)frame completionHandler:(void (^)(BOOL))done {
    id alert = [CLS("UIAlertController") alertControllerWithTitle:nil message:message preferredStyle:1];
    [alert addAction:[CLS("UIAlertAction") actionWithTitle:@"Cancel" style:1 handler:^(id a) { done(NO); }]];
    [alert addAction:[CLS("UIAlertAction") actionWithTitle:@"OK" style:0 handler:^(id a) { done(YES); }]];
    present(alert);
}
- (void)webView:(id)webView runJavaScriptTextInputPanelWithPrompt:(id)prompt defaultText:(id)text initiatedByFrame:(id)frame completionHandler:(void (^)(id))done {
    id alert = [CLS("UIAlertController") alertControllerWithTitle:nil message:prompt preferredStyle:1];
    [alert addTextFieldWithConfigurationHandler:^(id field) { [field setText:text]; }];
    [alert addAction:[CLS("UIAlertAction") actionWithTitle:@"Cancel" style:1 handler:^(id a) { done(nil); }]];
    [alert addAction:[CLS("UIAlertAction") actionWithTitle:@"OK" style:0 handler:^(id a) {
        done([[[alert textFields] firstObject] text]);
    }]];
    present(alert);
}
@end

int main(int argc, char *argv[]) {
    @autoreleasepool {
        return UIApplicationMain(argc, argv, nil, @"ChimiAppDelegate");
    }
}
