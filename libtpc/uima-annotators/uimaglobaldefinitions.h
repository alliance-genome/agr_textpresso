// Global file containing all global definitions.

#ifndef UIMAGLOBALDEFINITIONS_H
#define UIMAGLOBALDEFINITIONS_H

#include <uima/api.hpp>
#include <set>
#include <string>

// If a composite delimiter exists, then there cannot be another delimiter
// that is a subset of that composite token delimiter. Decompose it accordingly.
// This applies to token and sentence delimiter
namespace tp_uima_globals {

inline const UnicodeString* token_delimiters() {
    static const auto* values = new const UnicodeString[19]{
        " ", "\n", "\t", "'", "\"",
        "/", "—", "(", ")", "[",
        "]", "{", "}", ":", ". ",
        "; ", ", ", "! ", "? "
    };
    return values;
}

inline const UnicodeString* sentence_delimiters() {
    static const auto* values = new const UnicodeString[12]{
        ".\n", "!\n", "?\n", ". ", "! ", "? ",
        ".\t", "!\t", "?\t", ".<", "!<", "?<"
    };
    return values;
}

inline const UnicodeString* pdf_tags() {
    static const auto* values = new const UnicodeString[8]{
        "<_pdf _image", "<_pdf _sbr", "<_pdf _hbr", "<_pdf _fsc",
        "<_pdf _fnc", "<_pdf _ydiff", "<_pdf _cr", "<_pdf _page"
    };
    return values;
}

inline const std::set<UnicodeString>& sectionArticleB() {
    static const auto* values = new std::set<UnicodeString>{"Beginning of Article\n"};
    return *values;
}

inline const std::set<UnicodeString>& sectionArticleE() {
    static const auto* values = new std::set<UnicodeString>{"End of Article\n"};
    return *values;
}

inline const std::set<UnicodeString>& sectionAbstract() {
    static const auto* values = new std::set<UnicodeString>{
        "Abstract\n", "A b s t r a c t\n", "ABSTRACT\n", "A B S T R A C T\n"
    };
    return *values;
}

inline const std::set<UnicodeString>& sectionIntroduction() {
    static const auto* values = new std::set<UnicodeString>{
        "Introduction\n", "I n t r o d u c t i o n\n", "INTRODUCTION\n", "I N T R O D U C T I O N\n"
    };
    return *values;
}

inline const std::set<UnicodeString>& sectionResult() {
    static const auto* values = new std::set<UnicodeString>{
        "Result\n", "R e s u l t\n", "RESULT\n", "R E S U L T\n",
        "Results\n", "R e s u l t s\n", "RESULTS\n", "R E S U L T S\n"
    };
    return *values;
}

inline const std::set<UnicodeString>& sectionDiscussion() {
    static const auto* values = new std::set<UnicodeString>{
        "Discussion\n", "D i s c u s s i o n\n", "DISCUSSION\n", "D I S C U S S I O N\n"
    };
    return *values;
}

inline const std::set<UnicodeString>& sectionConclusion() {
    static const auto* values = new std::set<UnicodeString>{
        "Conclusion\n", "C o n c l u s i o n\n", "CONCLUSION\n", "C O N C L U S I O N\n",
        "Conclusions\n", "C o n c l u s i o n s\n", "CONCLUSIONS\n", "C O N C L U S I O N S\n"
    };
    return *values;
}

inline const std::set<UnicodeString>& sectionBackground() {
    static const auto* values = new std::set<UnicodeString>{
        "Background\n", "B a c k g r o u n d\n", "BACKGROUND\n", "B A C K G R O U N D\n"
    };
    return *values;
}

inline const std::set<UnicodeString>& sectionMaterialsMethods() {
    static const auto* values = new std::set<UnicodeString>{
        "Material\n", "M a t e r i a l\n", "MATERIAL\n", "M A T E R I A L\n",
        "Materials\n", "M a t e r i a l s\n", "MATERIALS\n", "M A T E R I A L S\n",
        "Method\n", "M e t h o d\n", "METHOD\n", "M E T H O D\n",
        "Methods\n", "M e t h o d s\n", "METHODS\n", "M E T H O D S\n",
        "Material and Method\n", "M a t e r i a l   a n d   M e t h o d\n", "MATERIAL AND METHOD\n",
        "M A T E R I A L   A N D   M E T H O D\n", "Material and Methods\n",
        "M a t e r i a l   a n d   M e t h o d s\n", "MATERIAL AND METHODS\n",
        "M A T E R I A L   A N D   M E T H O D S\n", "Materials and Method\n",
        "M a t e r i a l s   a n d  M e t h o d\n", "MATERIALS AND METHOD\n",
        "M A T E R I A L S   A N D   M E T H O D\n", "Materials and Methods\n",
        "M a t e r i a l s   a n d   M e t h o d s\n", "MATERIALS AND METHODS\n",
        "M A T E R I A L S   A N D   M E T H O D S\n", "Material And Method\n",
        "M a t e r i a l   A n d   M e t h o d\n", "Material And Methods\n",
        "M a t e r i a l   A n d   M e t h o d s\n", "Materials And Method\n",
        "M a t e r i a l s   A n d   M e t h o d\n", "Materials And Methods\n",
        "M a t e r i a l s   A n d   M e t h o d s", "Material and method\n",
        "M a t e r i a l   a n d   m e t h o d\n", "Material and methods\n",
        "M a t e r i a l   a n d   m e t h o d s\n", "Materials and method\n",
        "M a t e r i a l s   a n d   m e t h o d\n", "Materials and methods\n",
        "M a t e r i a l s   a n d   m e t h o d s\n"
    };
    return *values;
}

inline const std::set<UnicodeString>& sectionDesign() {
    static const auto* values = new std::set<UnicodeString>{
        "Design\n", "D e s i g n\n", "DESIGN\n", "D E S I G N\n",
        "Designs\n", "D e s i g n s\n", "DESIGNS\n", "D E S I G N S\n"
    };
    return *values;
}

inline const std::set<UnicodeString>& sectionAcknowledgments() {
    static const auto* values = new std::set<UnicodeString>{
        "Acknowledgment\n", "A c k n o w l e d g m e n t\n", "ACKNOWLEDGMENT\n", "A C K N O W L E D G M E N T\n",
        "Acknowledgments\n", "A c k n o w l e d g m e n t s\n", "ACKNOWLEDGMENTS\n", "A C K N O W L E D G M E N T S\n",
        "Acknowledgement\n", "A c k n o w l e d g e m e n t\n", "ACKNOWLEDGEMENT\n", "A C K N O W L E D G E M E N T\n",
        "Acknowledgements\n", "A c k n o w l e d g e m e n t s\n", "ACKNOWLEDGEMENTS\n", "A C K N O W L E D G E M E N T S\n"
    };
    return *values;
}

inline const std::set<UnicodeString>& sectionReferences() {
    static const auto* values = new std::set<UnicodeString>{
        "Reference\n", "R e f e r e n c e\n", "REFERENCE\n", "R E F E R E N C E\n",
        "References\n", "R e f e r e n c e s\n", "REFERENCES\n", "R E F E R E N C E S\n"
    };
    return *values;
}

inline const std::string* server_names() {
    static const auto* values = new const std::string[3]{
        "http://goldturtle.caltech.edu/cgi-bin/ReceivePost.cgi",
        "http://go-genkisugi.rhcloud.com/capella",
        "http://localhost/cgi-bin/ReceivePost.cgi"
    };
    return values;
}

inline const UnicodeString& pdf_tag_start() {
    static const auto* value = new UnicodeString("<_pdf ");
    return *value;
}

inline const UnicodeString& pdf_tag_end() {
    static const auto* value = new UnicodeString("/>");
    return *value;
}

}  // namespace tp_uima_globals

const int G_initT_No = 19;
const int G_initS_No = 12;
const int G_initP_No = 8;
const int ServerNames_No = 3;

#endif
