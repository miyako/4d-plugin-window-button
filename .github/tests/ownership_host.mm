// Engine contracts adapted from virtual-key 255b85d1ff69657f432de80f3aa499527d53f077.
#include "4DPluginAPI.h"
#include "PrivateTypes.h"
#include "EntryPoints.h"
#include "4DPlugin.h"
#include <codecvt>
#include <iostream>
#include <locale>
#include <type_traits>

static std::map<PA_Unichar*, size_t> strings;
static std::map<PA_Picture, int> pictures;
static std::map<PA_Handle, size_t> handles;
static bool nullEmpty, failCommand, failHandle, failResize, invalidWindow;
static int commandCalls, resultKind = 1, pointerReads, platformCalls, windowReads;
static CUTF16String expected;
static bool buttons[3], edited;
static OwnershipWindow* window;
static OwnershipButton* buttonObjects[3];

static void check(bool valid, const char* message)
{
    if (!valid) { std::cerr << message << "\n"; std::exit(1); }
}
static CUTF16String utf16(const char* text)
{
    std::wstring_convert<std::codecvt_utf8_utf16<char16_t>, char16_t> codec;
    auto converted = codec.from_bytes(text);
    return CUTF16String(reinterpret_cast<const PA_Unichar*>(converted.data()), converted.size());
}
static PA_Unistring makeString(const PA_Unichar* text)
{
    size_t units = 0;
    while (text && text[units]) ++units;
    PA_Unistring value = {};
    if (units || !nullEmpty) {
        value.fString = new PA_Unichar[units + 1];
        if (units) std::memcpy(value.fString, text, units * sizeof(PA_Unichar));
        value.fString[units] = 0;
        value.fLength = static_cast<PA_long32>(units);
        strings[value.fString] = units;
    }
    return value;
}
static void disposeString(PA_Unistring value)
{
    if (!value.fString) { check(value.fLength == 0, "null nonempty string"); return; }
    check(strings.count(value.fString), "duplicate/unowned string disposal");
    check(strings.at(value.fString) == static_cast<size_t>(value.fLength), "allocation length");
    strings.erase(value.fString); delete[] value.fString;
}
static void textEquals(PA_Unistring value, const CUTF16String& wanted)
{
    check(value.fLength == static_cast<PA_long32>(wanted.size()), "exact UTF16 length");
    check(value.fString || wanted.empty(), "missing text allocation");
    if (value.fString) {
        check(strings.count(value.fString), "read after string release");
        check(value.fString[value.fLength] == 0, "text terminator");
        check(CUTF16String(value.fString, value.fLength) == wanted, "exact UTF16 content");
    }
}
static PA_Picture makePicture()
{
    PA_Picture p = new unsigned char(42); pictures[p] = 1; return p;
}
static void releasePicture(PA_Picture p)
{
    if (!p) return;
    check(pictures.count(p), "duplicate/unowned picture disposal");
    if (--pictures[p] == 0) { pictures.erase(p); delete static_cast<unsigned char*>(p); }
}
static void clear(PA_Variable* v)
{
    if (v->fType == eVK_Unistring) disposeString(v->uValue.fString);
    else if (v->fType == eVK_Picture) releasePicture(v->uValue.fPicture);
    else if (v->fType == eVK_ArrayUnicode) {
        auto h = v->uValue.fArray.fData;
        check(handles.count(h), "invalid array handle");
        auto values = reinterpret_cast<PA_Unistring*>(*h);
        for (PA_long32 i = 0; i <= v->uValue.fArray.fNbElements; ++i) disposeString(values[i]);
        std::free(*h); delete h; handles.erase(h);
    } else check(v->fType == eVK_Undefined || v->fType == eVK_Longint,
                 "unsupported clear kind (including raw-kind0 failure)");
    v->fType = eVK_Undefined; v->fFiller = 0;
}
static void host(short selector, EngineBlock* eb)
{
    switch (selector) {
    case EX_CREATE_UNISTRING:
        eb->fUniString1 = makeString(reinterpret_cast<PA_Unichar*>(eb->fHandle)); break;
    case EX_DISPOSE_UNISTRING: disposeString(eb->fUniString1); break;
    case EX_SET_UNISTRING: {
        auto replacement = makeString(reinterpret_cast<PA_Unichar*>(eb->fHandle));
        disposeString(eb->fUniString1); eb->fUniString1 = replacement; break;
    }
    case EX_CREATE_PICTURE:
        check(eb->fParam1 == 0 || eb->fPtr1, "picture bytes missing");
        eb->fPicture = makePicture(); eb->fError = 0; break;
    case EX_DISPOSE_PICTURE: releasePicture(eb->fPicture); break;
    case EX_DUPLICATE_PICTURE:
        if (!eb->fPicture) break;
        check(pictures.count(eb->fPicture), "retain dead picture");
        if (eb->fParam1 == 0) ++pictures[eb->fPicture];
        else eb->fPicture = makePicture();
        break;
    case EX_GET_PICTURE_DATA:
        check(pictures.count(eb->fPicture), "enumerate dead picture");
        // Successful metadata ownership is unspecified by this SDK; do not invent it.
        eb->fError = eER_IncompatibleTypes;
        eb->fUniString1.fLength = -1;
        eb->fUniString1.fString = reinterpret_cast<PA_Unichar*>(1);
        break;
    case EX_CLEAR_VARIABLE: clear(static_cast<PA_Variable*>(eb->fPtr1)); break;
    case EX_GET_INFORMATION: eb->fParam1 = 0; eb->fParam2 = 0x1600; break;
    case EX_GET_HWND:
        ++windowReads;
        check(reinterpret_cast<sLONG_PTR>(eb->fHandle) == 41, "unexpected synthetic window ID");
        eb->fHandle = invalidWindow ? nullptr : reinterpret_cast<PA_Handle>(window);
        eb->fError = 0;
        break;
    case EX_YIELD_ABSOLUTE: break;
    case EX_GET_POINTER_VALUE_PROPERTIES:
        eb->fParam1 = eVK_Unistring; eb->fParam2 = 0; eb->fParam3 = 0; eb->fError = 0; break;
    case EX_FIELD_ATTRIBUTES:
        check(eb->fTable == 12 && eb->fField == 34, "unexpected synthetic field");
        eb->fParam1 = eFK_TextField; eb->fParam2 = 0; eb->fParam3 = 0; eb->fError = 0; break;
    case EX_GET_POINTER_VALUE: {
        ++pointerReads;
        auto v = reinterpret_cast<PA_Variable*>(eb->fHandle);
        *v = PA_CreateVariable(eVK_Undefined);
        auto owned = makeString(expected.c_str()); PA_SetStringVariable(v, &owned);
        eb->fError = 0; break;
    }
    case EX_HANDLE_MANAGER: {
        auto h = eb->fHandle;
        switch (eb->fParam1) {
        case 1:
            if (failHandle) { eb->fHandle = nullptr; eb->fError = eER_IncompatibleTypes; break; }
            h = new char*;
            *h = static_cast<char*>(std::calloc(1, std::max<sLONG_PTR>(1, eb->fParam2)));
            check(*h, "test handle allocation failed");
            handles[h] = eb->fParam2; eb->fHandle = h; break;
        case 2:
            check(handles.count(h), "dispose dead handle");
            std::free(*h); delete h; handles.erase(h); break;
        case 3: {
            check(handles.count(h), "resize dead handle");
            if (failResize) { eb->fError = eER_IncompatibleTypes; break; }
            auto data = static_cast<char*>(std::realloc(*h, std::max<sLONG_PTR>(1, eb->fParam2)));
            check(data, "test resize allocation failed");
            *h = data; handles[h] = eb->fParam2; break;
        }
        case 4: check(handles.count(h), "size dead handle"); eb->fParam2 = handles[h]; break;
        case 5: check(handles.count(h), "lock dead handle"); eb->fParam3 = reinterpret_cast<sLONG_PTR>(*h); break;
        case 6: check(handles.count(h), "unlock dead handle"); break;
        default: check(false, "unexpected handle operation");
        }
        break;
    }
    case EX_CONVERT_CHARSET_TO_CHARSET: {
        std::wstring_convert<std::codecvt_utf8_utf16<char16_t>, char16_t> codec;
        size_t bytes;
        if (eb->fParam2 == eVTC_UTF_8 && eb->fParam4 == eVTC_UTF_16) {
            auto in = static_cast<char*>(eb->fPtr1);
            auto out = codec.from_bytes(in, in + eb->fParam1);
            bytes = out.size() * sizeof(PA_Unichar);
            check(bytes + sizeof(PA_Unichar) <= static_cast<size_t>(eb->fParam3), "UTF16 capacity bytes");
            std::memcpy(eb->fPtr2, out.data(), bytes);
            std::memset(static_cast<char*>(eb->fPtr2) + bytes, 0, sizeof(PA_Unichar));
        } else {
            check(eb->fParam2 == eVTC_UTF_16 && eb->fParam4 == eVTC_UTF_8, "conversion direction");
            auto in = static_cast<char16_t*>(eb->fPtr1);
            auto out = codec.to_bytes(in, in + eb->fParam1 / sizeof(PA_Unichar));
            bytes = out.size();
            check(bytes + 1 <= static_cast<size_t>(eb->fParam3), "UTF8 capacity bytes");
            std::memcpy(eb->fPtr2, out.data(), bytes);
            static_cast<char*>(eb->fPtr2)[bytes] = 0;
        }
        eb->fParam3 = bytes; eb->fError = 0; break;
    }
    case EX_EXECUTE_COMMAND_BY_ID: {
        ++commandCalls;
        auto args = static_cast<PA_Variable**>(eb->fPtr1);
        auto result = static_cast<PA_Variable*>(eb->fPtr2);
        check(result->fType == eVK_Undefined, "command return initialization");
        if (failCommand) {
            std::memset(result, 0xa5, sizeof(*result));
            if (resultKind == 0) result->fType = 0;
            eb->fError = eER_IncompatibleTypes; break;
        }
        if (eb->fParam1 == 678) {
            textEquals(args[0]->uValue.fString, expected);
            clear(args[1]); PA_SetPictureVariable(args[1], makePicture());
        } else if (eb->fParam1 == 1002) {
            textEquals(args[1]->uValue.fString, expected);
            clear(args[0]); PA_SetPictureVariable(args[0], makePicture());
        } else if (eb->fParam1 == 988) {
            clear(args[0]); PA_SetPictureVariable(args[0], makePicture());
        } else if (eb->fParam1 == 457) {
            check(pictures.count(args[0]->uValue.fPicture), "size input dead");
            PA_SetLongintVariable(args[1], 23); PA_SetLongintVariable(args[2], 17);
        } else if (eb->fParam1 == 679) {
            check(pictures.count(args[0]->uValue.fPicture), "thumbnail input dead");
            clear(args[1]); PA_SetPictureVariable(args[1], makePicture());
        } else check(false, "unexpected command");
        if (resultKind == 1) {
            auto owned = makeString(expected.c_str()); PA_SetStringVariable(result, &owned);
        } else if (resultKind == 2) PA_SetPictureVariable(result, makePicture());
        eb->fError = 0; break;
    }
    default: std::cerr << "unexpected engine selector " << selector << "\n"; std::exit(1);
    }
}

@implementation OwnershipURL
- (id)initWithString:(NSString *)value { ++platformCalls; return [super init]; }
- (NSString *)absoluteString { return @"synthetic"; }
@end
@implementation OwnershipImage
- (id)initWithCGImage:(CGImageRef)image size:(NSSize)size { ++platformCalls; return [super init]; }
- (NSData *)TIFFRepresentation { ++platformCalls; return [NSData dataWithBytes:"123" length:3]; }
@end
@implementation OwnershipButton
- (void)setEnabled:(BOOL)value
{
    ++platformCalls;
    for (int i = 0; i < 3; ++i) if (self == buttonObjects[i]) { buttons[i] = value; return; }
    check(false, "unknown synthetic button");
}
- (BOOL)isEnabled
{
    ++platformCalls;
    for (int i = 0; i < 3; ++i) if (self == buttonObjects[i]) return buttons[i];
    check(false, "unknown synthetic button"); return NO;
}
@end
@implementation OwnershipWindow
- (OwnershipButton *)standardWindowButton:(NSWindowButton)button
{
    check(button == NSWindowCloseButton || button == NSWindowMiniaturizeButton ||
          button == NSWindowZoomButton, "unexpected window button");
    return buttonObjects[button];
}
- (void)setDocumentEdited:(BOOL)value { ++platformCalls; edited = value; }
- (BOOL)isDocumentEdited { ++platformCalls; return edited; }
@end
CFURLRef OwnershipCreateURL(CFAllocatorRef, CFStringRef, CFURLPathStyle, Boolean)
{ ++platformCalls; return reinterpret_cast<CFURLRef>([[OwnershipURL alloc] init]); }
CFStringRef OwnershipCopyPath(CFURLRef, CFURLPathStyle)
{ ++platformCalls; return reinterpret_cast<CFStringRef>([[NSString alloc] initWithString:@"synthetic"]); }
void OwnershipLog(NSString*, ...) { ++platformCalls; }
void OwnershipScaleContext(CGContextRef, CGFloat, CGFloat)
{ check(false, "unexpected graphics context scaling"); }
void OwnershipTranslateContext(CGContextRef, CGFloat, CGFloat)
{ check(false, "unexpected graphics context translation"); }
static int attributeIndex(int attribute)
{
    if (attribute == kHIWindowBitCloseBox) return 0;
    if (attribute == kHIWindowBitCollapseBox) return 1;
    check(attribute == kHIWindowBitZoomBox, "unexpected Carbon attribute"); return 2;
}
OSStatus OwnershipChangeAttributes(WindowRef ref, const int* set, const int* unset)
{
    check(ref == reinterpret_cast<WindowRef>(window), "unexpected Carbon window");
    check((set != nullptr) != (unset != nullptr), "Carbon attribute direction");
    const int* attrs = set ? set : unset;
    check(attrs[1] == 0, "Carbon attributes terminator");
    ++platformCalls; buttons[attributeIndex(attrs[0])] = set != nullptr; return noErr;
}
Boolean OwnershipTestAttribute(WindowRef ref, int attribute)
{
    check(ref == reinterpret_cast<WindowRef>(window), "unexpected Carbon window");
    ++platformCalls; return buttons[attributeIndex(attribute)];
}
OSStatus OwnershipSetModified(WindowRef ref, Boolean value)
{
    check(ref == reinterpret_cast<WindowRef>(window), "unexpected Carbon window");
    ++platformCalls; edited = value; return noErr;
}
Boolean OwnershipIsModified(WindowRef ref)
{
    check(ref == reinterpret_cast<WindowRef>(window), "unexpected Carbon window");
    ++platformCalls; return edited;
}

static void pictureCase(const std::string& name, const char* text)
{
    PA_Picture handoff = nullptr, returned = nullptr, param = makePicture();
    {
        CPicture picture;
        if (name == "path") {
            CUTF8String path(reinterpret_cast<const uint8_t*>(text)); picture.fromFileAtPath(&path);
        } else if (name == "bytes") {
            const uint8_t synthetic[] = {1, 2, 3};
            for (int i = 0; i < 20; ++i) picture.setBytes(synthetic, sizeof(synthetic));
        } else if (name == "copy") handoff = picture.createCopy(text);
        else if (name == "gray") handoff = picture.createGrayScale();
        else if (name == "size") {
            unsigned width = 90, height = 91; picture.getSize(&width, &height);
            check(width == (failCommand || failHandle ? 0u : 23u) &&
                  height == (failCommand || failHandle ? 0u : 17u), "legacy size outputs");
        } else if (name == "thumbnail") handoff = picture.createThumbnail(23, 17);
        else check(false, "unknown picture test");
        bool aliasesInput = handoff && handoff == picture.getPicture();
        if (handoff) check(pictures[handoff] == (aliasesInput ? 2 : 1), "handoff owned reference");
        check(pictures.count(picture.getPicture()), "wrapper died during callback");
        picture.setReturn(reinterpret_cast<sLONG_PTR*>(&returned));
        check(pictures[returned] == (aliasesInput ? 3 : 2), "independently retained return");
        BytePtr params[] = {reinterpret_cast<BytePtr>(&param)};
        picture.toParamAtIndex(params, 1);
        check(param == returned && pictures[param] == (aliasesInput ? 4 : 3), "independently retained parameter");
    }
    check(pictures.count(returned) && pictures[returned] == (handoff == returned ? 3 : 2), "output survives wrapper");
    PA_DisposePicture(returned); PA_DisposePicture(param);
    if (handoff) PA_DisposePicture(handoff);
}
static void scalarCase()
{
    auto input = PA_CreateUnistring(const_cast<PA_Unichar*>(expected.c_str()));
    auto result = PA_CreateUnistring(nullptr), output = PA_CreateUnistring(nullptr);
    {
        C_TEXT wrapper;
        BytePtr params[] = {reinterpret_cast<BytePtr>(&input)};
        wrapper.fromParamAtIndex(params, 1);
        auto changed = utf16("changed"); PA_SetUnistring(&input, const_cast<PA_Unichar*>(changed.c_str()));
        params[0] = reinterpret_cast<BytePtr>(&output); wrapper.toParamAtIndex(params, 1);
        auto resultPtr = &result; wrapper.setReturn(reinterpret_cast<sLONG_PTR*>(&resultPtr));
    }
    textEquals(result, expected); textEquals(output, expected);
    PA_DisposeUnistring(&input); PA_DisposeUnistring(&output); PA_DisposeUnistring(&result);
}
static void arrayCase()
{
    auto arr = PA_CreateVariable(eVK_ArrayUnicode); PA_ResizeArray(&arr, 4);
    const char* fixtures[] = {"ASCII", "\xe6\x97\xa5", "\xf0\x9f\x98\x80", "", ""};
    for (int i = 0; i <= 4; ++i) {
        auto text = utf16(fixtures[i]); auto owned = PA_CreateUnistring(const_cast<PA_Unichar*>(text.c_str()));
        PA_SetStringInArray(arr, i, &owned);
    }
    BytePtr params[] = {reinterpret_cast<BytePtr>(&arr)};
    ARRAY_TEXT copy; copy.fromParamAtIndex(params, 1);
    auto changed = utf16("replacement");
    auto replacement = PA_CreateUnistring(const_cast<PA_Unichar*>(changed.c_str()));
    PA_SetStringInArray(arr, 0, &replacement);
    for (int repeat = 0; repeat < 20; ++repeat) {
        auto churn = PA_CreateUnistring(const_cast<PA_Unichar*>(changed.c_str())); PA_DisposeUnistring(&churn);
        copy.toParamAtIndex(params, 1);
        for (int i = 0; i <= 4; ++i) textEquals(PA_GetStringInArray(arr, i), utf16(fixtures[i]));
    }
    auto reject = PA_CreateUnistring(const_cast<PA_Unichar*>(changed.c_str()));
    PA_SetStringInArray(arr, -1, &reject); PA_SetStringInArray(arr, 5, &reject);
    auto wrong = PA_CreateVariable(eVK_Longint); PA_SetStringInArray(wrong, 0, &reject);
    auto missing = arr; missing.uValue.fArray.fData = nullptr;
    PA_SetStringInArray(missing, 0, &reject); PA_SetStringInArray(arr, 0, nullptr);
    textEquals(reject, changed); PA_DisposeUnistring(&reject);
    copy.toParamAtIndex(params, 0);
    copy.setSize(2); copy.toParamAtIndex(params, 1);
    copy.setSize(0); copy.toParamAtIndex(params, 1); PA_ClearVariable(&arr);
    arr = PA_CreateVariable(eVK_Undefined);
    copy.appendUTF16String(changed.c_str()); copy.toParamAtIndex(params, 1); PA_ClearVariable(&arr);
}
static void sdkFailureCase()
{
    failHandle = true;
    auto result = PA_ExecuteCommandByID(457, nullptr, 0);
    check(result.fType == 0 && PA_GetLastError() != eER_NoErr, "raw-kind0 command failure");
    check(PA_GetVariableKind(result) == eVK_Unistring, "raw-kind0 normalization");
    failHandle = false;
    auto arr = PA_CreateVariable(eVK_ArrayUnicode);
    auto bytes = PA_GetHandleSize(arr.uValue.fArray.fData);
    failResize = true; PA_ResizeArray(&arr, 7);
    check(arr.uValue.fArray.fNbElements == 7, "SDK failure changes logical count");
    check(PA_GetHandleSize(arr.uValue.fArray.fData) == bytes, "SDK failure preserves physical size");
    failResize = false;
    arr.uValue.fArray.fNbElements = 0; // Repair only the synthetic descriptor for cleanup.
    PA_ClearVariable(&arr);
}
static void pointerCase(bool field)
{
    const char kinds[] = {26, 9, 35, 13};
    for (int scope = 0; scope < (field ? 1 : 4); ++scope) {
        C_POINTER wrapper;
        PointerBlock pointer = {}; pointer.fClass = field ? 0 : 1; pointer.fScope = scope;
        if (field) { pointer.uValue.fTableField.fTable = 12; pointer.uValue.fTableField.fField = 34; }
        else {
            pointer.uValue.fVariable.fTag = 123; pointer.uValue.fVariable.fIndice = 456;
            pointer.uValue.fVariable.fName[0] = 'x';
        }
        BytePtr params[] = {reinterpret_cast<BytePtr>(&pointer)}; wrapper.fromParamAtIndex(params, 1);
        auto output = PA_CreateVariable(eVK_Undefined); wrapper.getVariable(&output);
        check(pointerReads == 0, "reference construction fetched an owning value");
        check(output.fType == (field ? 3 : kinds[scope]) && output.fFiller == 1, "reference kind");
        if (field) {
            check(output.uValue.fTableFieldDefinition.fTableNumber == 12 &&
                  output.uValue.fTableFieldDefinition.fFieldNumber == 34, "field reference metadata");
        } else {
            check(output.uValue.fVariableDefinition.fTag == 123 &&
                  output.uValue.fVariableDefinition.fIndice == 456 &&
                  output.uValue.fVariableDefinition.fType == scope &&
                  output.uValue.fVariableDefinition.fName[0] == 'x', "variable reference metadata");
        }
    }
}
template<typename T> static void pinCopyPicture(T&) {}
static void pinCopyPicture(CPicture& source)
{
    // Isolate the raw CBytes double-delete from the earlier duplicate picture release.
    PA_DuplicatePicture(source.getPicture(), 1);
}
template<typename T, typename std::enable_if<std::is_copy_constructible<T>::value, int>::type = 0>
static void copyProbe()
{
    T source; pinCopyPicture(source); { T alias(source); }
}
template<typename T, typename std::enable_if<!std::is_copy_constructible<T>::value, int>::type = 0>
static void copyProbe()
{
    check(!std::is_copy_assignable<T>::value, "owning wrapper shallow-copy assignment");
}
static void traits(const std::string& name)
{
    if (name == "C_TEXT") copyProbe<C_TEXT>();
    else if (name == "ARRAY_TEXT") copyProbe<ARRAY_TEXT>();
    else if (name == "CPicture") copyProbe<CPicture>();
    else if (name == "C_PICTURE") copyProbe<C_PICTURE>();
    else if (name == "C_BLOB") copyProbe<C_BLOB>();
    else if (name == "ARRAY_BOOLEAN") copyProbe<ARRAY_BOOLEAN>();
    else if (name == "ARRAY_DATE") copyProbe<ARRAY_DATE>();
    else if (name == "ARRAY_INTEGER") copyProbe<ARRAY_INTEGER>();
    else if (name == "ARRAY_LONGINT") copyProbe<ARRAY_LONGINT>();
    else if (name == "ARRAY_REAL") copyProbe<ARRAY_REAL>();
    else if (name == "ARRAY_TIME") copyProbe<ARRAY_TIME>();
    else if (name == "values") {
        check(std::is_copy_constructible<C_DATE>::value && std::is_copy_constructible<CBytes>::value &&
              std::is_copy_constructible<C_POINTER>::value && std::is_copy_constructible<C_LONGINT>::value &&
              std::is_copy_constructible<C_INTEGER>::value && std::is_copy_constructible<C_REAL>::value &&
              std::is_copy_constructible<C_TIME>::value, "value and borrowed types remain copyable");
    } else check(false, "unknown trait");
}
static void dispatchCase()
{
    window = [[OwnershipWindow alloc] init];
    for (int i = 0; i < 3; ++i) buttonObjects[i] = [[OwnershipButton alloc] init];
    int win = 41, attribute = 0, enabled = 0, result = -1;
    BytePtr params[] = {reinterpret_cast<BytePtr>(&win), reinterpret_cast<BytePtr>(&attribute),
                        reinterpret_cast<BytePtr>(&enabled)};
    PluginBlock block = {}; block.fParameters = params; block.fResult = &result;
    for (int choice : {0, 1, 2, 3, -1, 99}) {
        attribute = choice;
        for (int value : {0, 1}) {
            enabled = value; PluginMain(1, &block); PluginMain(2, &block);
            check(result == value, "dispatcher button/modified behavior");
        }
    }
    invalidWindow = true;
    int before = platformCalls;
    PluginMain(1, &block); result = -1; PluginMain(2, &block);
    check(result == 0 && platformCalls == before, "invalid window no-op/zero");
    int reads = windowReads;
    CommandDispatcher(999, reinterpret_cast<sLONG_PTR*>(&result), params);
    check(windowReads == reads && commandCalls == 0, "unknown selector no-op");
    check(windowReads == 26 && platformCalls == 24, "exact synthetic UI call counts");
    for (auto object : buttonObjects) [object release];
    [window release]; window = nil;
}
int main(int argc, char** argv)
{
    @autoreleasepool {
        check(argc >= 2, "test name required"); gCall4D = host;
        std::string name = argv[1]; const char* text = argc >= 3 ? argv[2] : ""; expected = utf16(text);
        nullEmpty = argc >= 4 && std::string(argv[3]) == "null";
        if (name == "arrays") arrayCase();
        else if (name == "scalar") scalarCase();
        else if (name == "sdk-failures") sdkFailureCase();
        else if (name == "pointer") pointerCase(false);
        else if (name == "pointer-field") pointerCase(true);
        else if (name == "traits") traits(text);
        else if (name == "dispatch") dispatchCase();
        else {
            check(argc == 7, "picture arguments");
            resultKind = std::stoi(argv[4]);
            failCommand = std::string(argv[5]) == "command";
            failHandle = std::string(argv[5]) == "handle";
            pictureCase(argv[6], text);
        }
        check(strings.empty(), "unbalanced string allocations");
        check(pictures.empty(), "unbalanced picture references"); check(handles.empty(), "unbalanced handles");
        std::cout << "PASS " << name << " strings=0 pictures=0 handles=0"
                  << " objects=n/a collections=n/a commands=" << commandCalls
                  << " synthetic_UI=" << platformCalls << "\n";
    }
}
