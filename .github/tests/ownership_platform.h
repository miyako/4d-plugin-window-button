#import <Carbon/Carbon.h>
#import <Cocoa/Cocoa.h>
#include <cstring>

// Force-included before every production source. No real platform object escapes.
@interface OwnershipURL : NSObject
- (id)initWithString:(NSString *)value;
- (NSString *)absoluteString;
@end
@interface OwnershipImage : NSObject
- (id)initWithCGImage:(CGImageRef)image size:(NSSize)size;
- (NSData *)TIFFRepresentation;
@end
@interface OwnershipButton : NSObject
- (void)setEnabled:(BOOL)value;
- (BOOL)isEnabled;
@end
@interface OwnershipWindow : NSObject
- (OwnershipButton *)standardWindowButton:(NSWindowButton)button;
- (void)setDocumentEdited:(BOOL)value;
- (BOOL)isDocumentEdited;
@end
CFURLRef OwnershipCreateURL(CFAllocatorRef, CFStringRef, CFURLPathStyle, Boolean);
CFStringRef OwnershipCopyPath(CFURLRef, CFURLPathStyle);
void OwnershipLog(NSString*, ...);
OSStatus OwnershipChangeAttributes(WindowRef, const int*, const int*);
Boolean OwnershipTestAttribute(WindowRef, int);
OSStatus OwnershipSetModified(WindowRef, Boolean);
Boolean OwnershipIsModified(WindowRef);
void OwnershipScaleContext(CGContextRef, CGFloat, CGFloat);
void OwnershipTranslateContext(CGContextRef, CGFloat, CGFloat);
#define NSURL OwnershipURL
#define NSImage OwnershipImage
#define NSWindow OwnershipWindow
#define CFURLCreateWithFileSystemPath OwnershipCreateURL
#define CFURLCopyFileSystemPath OwnershipCopyPath
#define NSLog OwnershipLog
#define HIWindowChangeAttributes OwnershipChangeAttributes
#define HIWindowTestAttribute OwnershipTestAttribute
#define SetWindowModified OwnershipSetModified
#define IsWindowModified OwnershipIsModified
#define CGContextScaleCTM OwnershipScaleContext
#define CGContextTranslateCTM OwnershipTranslateContext
