/* 
 * File:   TdTokenizer.cpp
 * Author: mueller
 * 
 * Created on December 13, 2021, 2:15 PM
 */

#include "TdTokenizer.h"
#include "../uimaglobaldefinitions.h"
#include "textAndImageManager.h"
#include <boost/regex.hpp>
#include <boost/filesystem.hpp>
#include <sstream>
#include <iomanip>

using namespace std;
using namespace boost::filesystem;

/* magic numbers from http://www.isthe.com/chongo/tech/comp/fnv/ */
static const uint64_t InitialFNV = 14695981039346656037U;
static const uint64_t FNVMultiple = 1099511628211;

/* Fowler / Noll / Vo (FNV) Hash */
string tpfnv(const UnicodeStringRef &s) {
    uint64_t hash = InitialFNV;
    for (uint64_t i = 0; i < s.length(); i++) {
        hash = hash ^ (s[i]); /* xor  the low 8 bits */
        hash = hash * FNVMultiple; /* multiply by the magic number */
    }
    stringstream shex;
    shex << setw(16) << setfill('0') << hex << hash;
    return shex.str();
}

pair<int32_t, int32_t> MaximizeBoundaries(pair<int32_t, int32_t> i,
        pair<int32_t, int32_t> j) {
    // need to make these modifications (offsets) because
    // trie class has different boundary convention than UIMA
    int32_t ifi = i.first;
    int32_t ise = i.second + 1;
    int32_t jfi = j.first;
    int32_t jse = j.second + 1;
    if (ifi != jfi) {
        if (ise != jse) {
            // at least one boundaries needs to be the same;
            // return error code -1.
            return make_pair(-1, -1);
        } else {
            // upper boundary is the same;
            // adjust lower boundary.
            return make_pair((ifi < jfi) ? ifi : jfi, ise);
        }
    } else {
        // lower boundary is the same;
        // adjust upper boundary (trivial if upper boundary are the same).
        return make_pair(ifi, (ise > jse) ? ise : jse);
    }
}

void WriteOutAnnotations(CAS & tcas, const UnicodeStringRef usdocref,
        vector< pair<int32_t, int32_t> > & p, Type t, Feature f,
        AnnotationCounter & ac, bool writeoutdelimiters) {
    FSIndexRepository & indexRep = tcas.getIndexRepository();
    vector< pair<int32_t, int32_t> > merged;
    merged.clear();
    vector< pair<int32_t, int32_t> >::iterator it = p.begin();
    while (it < p.end()) {
        vector< pair<int32_t, int32_t> >::iterator it2 = it + 1;
        pair<int32_t, int32_t> res = MaximizeBoundaries(*it, *it2);
        if (res.first < 0) {
            res = make_pair((*it).first, (*it).second + 1);
        } else {
            it++;
        }
        merged.push_back(res);
        it++;
    }
    // use unique beginnings and endings of delimiters to annotate items at hand.
    int32_t laste = 0;
    for (it = merged.begin(); it != merged.end(); it++) {
        int32_t b = (*it).first;
        int32_t e = (*it).second;
        if (b != laste) {
            AnnotationFS fsNewTok = tcas.createAnnotation(t, laste, b);
            UnicodeString wd;
            usdocref.extract(laste, b - laste, wd);
            fsNewTok.setStringValue(f, wd);
            Feature faid = t.getFeatureByBaseName("aid");
            if (faid.isValid())
                fsNewTok.setIntValue(faid, ac.GetNextId());
            indexRep.addFS(fsNewTok);
        }
        laste = e;
        if (writeoutdelimiters) {
            AnnotationFS fsNewTok = tcas.createAnnotation(t, b, e);
            UnicodeString wd;
            usdocref.extract(b, e - b, wd);
            fsNewTok.setStringValue(f, wd);
            Feature faid = t.getFeatureByBaseName("aid");
            if (faid.isValid())
                fsNewTok.setIntValue(faid, ac.GetNextId());
            indexRep.addFS(fsNewTok);
        }
    }
}

vector< pair<int32_t, int32_t> > RemoveDelimiters(const UnicodeStringRef usdocref,
        vector<string> & regex,
        vector< pair<int32_t, int32_t> > & p,
        int32_t mfcl, int32_t mbcl) {
    vector< pair<int32_t, int32_t> > result;
    vector< pair<int32_t, int32_t> >::iterator it;
    for (it = p.begin(); it != p.end(); it++) {
        int32_t b = (*it).first;
        int32_t e = (*it).second + 1;
        string strip;
        usdocref.extract(b - mfcl, e - b + mfcl + mbcl, strip);
        bool matches = false;
        vector<string>::iterator is;
        for (is = regex.begin(); is != regex.end(); is++) {
            boost::regex expr(*is);
            matches = (matches || boost::regex_search(strip, expr));
        }
        if (!matches) {
            result.push_back(*it);
        } else {
            b = ((b - 100 > 0)) ? b - 100 : 0;
            usdocref.extract(b, 200, strip);
        }
    }
    return result;
}

// The raw document text carries inline PDF layout markers produced by text
// extraction (e.g. "<_pdf _cr/>", "<_pdf _fsc=+11/>") interspersed directly
// in the character stream. A section heading is typically followed by one
// of these markers before the actual line break -- e.g. the literal text
// "References <_pdf _cr/>\n" -- which never contains the exact substring
// "References\n" that the section trie searches for, so headings never
// match and no section boundaries are ever detected. This builds a copy of
// the text with every "<_pdf ...>" marker removed, and any space left
// dangling directly before a newline as a result (the marker is almost
// always preceded by a word-separating space) collapsed away, while
// recording, for each character kept, its offset in the original text so
// match positions found in the cleaned copy can be translated back to the
// original document for annotation creation.
UnicodeString CleanPdfTagsForSectionSearch(const UnicodeString & src,
        vector<int32_t> & posmap) {
    static const UnicodeString tagPrefix("<_pdf ");
    UnicodeString cleaned;
    posmap.clear();
    int32_t n = src.length();
    bool pendingSpace = false;
    int32_t pendingSpacePos = -1;
    for (int32_t i = 0; i < n;) {
        if (i + tagPrefix.length() <= n &&
                src.compare(i, tagPrefix.length(), tagPrefix) == 0) {
            int32_t j = i + tagPrefix.length();
            while (j < n && src.charAt(j) != '>') j++;
            if (j < n) j++; // consume the closing '>'
            i = j;
            continue;
        }
        UChar c = src.charAt(i);
        if (c == ' ') {
            if (pendingSpace) {
                cleaned.append((UChar) ' ');
                posmap.push_back(pendingSpacePos);
            }
            pendingSpace = true;
            pendingSpacePos = i;
        } else if (c == '\n') {
            pendingSpace = false; // drop dangling space before the newline
            cleaned.append(c);
            posmap.push_back(i);
        } else {
            if (pendingSpace) {
                cleaned.append((UChar) ' ');
                posmap.push_back(pendingSpacePos);
                pendingSpace = false;
            }
            cleaned.append(c);
            posmap.push_back(i);
        }
        i++;
    }
    if (pendingSpace) {
        cleaned.append((UChar) ' ');
        posmap.push_back(pendingSpacePos);
    }
    return cleaned;
}

// Some journals' articles print their bibliography as a bare numbered
// list with no "References" (or any other registered synonym) heading
// text anywhere in the document -- no literal-string trie match can ever
// find a heading that was never printed, so this scans for the numbered-
// list pattern itself as a fallback signal. Added 2026-08-14 after
// auditing a batch of SorghumBase zero-section papers and finding several
// genuinely well-structured papers permanently blocked on this exact
// case; generalized the same day after the first version (position-gated
// to the back half of the document, format-gated to "N. Author..." all on
// one line) turned out to miss a second real variant: modern Nature-family
// papers that place references right after the main text (as little as
// ~25% through the document, followed by the full Methods and dozens of
// pages of Extended Data figures) and whose text extraction sometimes
// splits the citation number onto its own line, separate from the author
// name ("2.\nRich-Griffin, C. et al...." rather than "2. Rich-Griffin, C.
// et al....").
//
// Per-match pattern: newline, 1-3 digits, '.', then whitespace (spaces/
// tabs, or up to one newline to cover the split-line case above), then an
// uppercase letter -- the start of an author surname. Position is no
// longer used as a filter (references can legitimately sit anywhere from
// roughly a quarter of the way through a modern paper to the very end of
// an older one) -- instead, each candidate match must be followed within
// a short window by a parenthesized 4-digit year, "(2006)"/"(2020)" style,
// which is close to universal for a real citation and essentially never
// occurs in an unrelated numbered list (protocol steps, supplementary
// item lists). This is a stronger and more format-independent signal than
// position ever was.
//
// Because position is no longer a filter, matches are then clustered by
// proximity (kMaxGap) and only the largest tight cluster is used, ending
// shortly after its own last entry -- not "run to End of Article" -- so a
// modern paper's references don't swallow the many unrelated pages of
// Methods and Extended Data that typically follow them.
//
// Operates on the same PDF-tag-cleaned buffer the heading trie searches
// (CleanPdfTagsForSectionSearch above), for the same reason that cleanup
// exists: a marker sitting between the newline and the digits would
// otherwise break the match. Returns [-1,-1] (in the cleaned buffer's own
// coordinates -- the caller maps back through posmap) if no qualifying
// span was found.
pair<int32_t, int32_t> DetectImplicitReferencesSpan(const UnicodeString & cleaned) {
    static const size_t kMinMatches = 5;
    static const int32_t kYearWindow = 400;   // chars to look ahead for "(YYYY)"
    static const int32_t kMaxGap = 600;       // chars between entries before a cluster breaks
    static const int32_t kTrailingBuffer = 500; // chars kept past the last entry in a cluster
    int32_t len = cleaned.length();
    vector<int32_t> matchPositions;
    for (int32_t i = 0; i < len - 3; i++) {
        if (cleaned.charAt(i) != (UChar) '\n') continue;
        int32_t j = i + 1;
        int32_t numStart = j;
        while (j < len && (j - numStart) < 3 &&
                cleaned.charAt(j) >= (UChar) '0' && cleaned.charAt(j) <= (UChar) '9') j++;
        if (j == numStart) continue; // no digits right after the newline
        if (j >= len || cleaned.charAt(j) != (UChar) '.') continue;
        j++;
        int32_t wsStart = j;
        int32_t newlineCount = 0;
        while (j < len && newlineCount <= 1 &&
                (cleaned.charAt(j) == (UChar) ' ' || cleaned.charAt(j) == (UChar) '\t' ||
                 cleaned.charAt(j) == (UChar) '\n')) {
            if (cleaned.charAt(j) == (UChar) '\n') newlineCount++;
            j++;
        }
        if (j == wsStart) continue; // require whitespace (or one newline) right after the period
        if (j >= len || cleaned.charAt(j) < (UChar) 'A' || cleaned.charAt(j) > (UChar) 'Z') continue;
        // require a parenthesized 4-digit year within the next kYearWindow
        // characters -- the real per-entry bibliography signal, now doing
        // the work position used to do.
        bool hasYear = false;
        int32_t scanEnd = min(j + kYearWindow, len - 6);
        for (int32_t k = j; k < scanEnd; k++) {
            if (cleaned.charAt(k) != (UChar) '(') continue;
            bool allDigits = true;
            for (int32_t d = 1; d <= 4; d++)
                if (cleaned.charAt(k + d) < (UChar) '0' || cleaned.charAt(k + d) > (UChar) '9')
                    allDigits = false;
            if (allDigits && cleaned.charAt(k + 5) == (UChar) ')') { hasYear = true; break; }
        }
        if (!hasYear) continue;
        matchPositions.push_back(i + 1); // position of the digit itself
    }
    if (matchPositions.size() < kMinMatches) return make_pair(-1, -1);
    // cluster by proximity; keep only the largest tight cluster, so an
    // isolated qualifying match far from the real bibliography (a false
    // positive that individually passed the year check) can't drag the
    // span out or get chosen over the real list.
    vector< pair<int32_t, int32_t> > clusters; // [firstIdx, lastIdx] into matchPositions
    size_t clusterStart = 0;
    for (size_t k = 1; k <= matchPositions.size(); k++) {
        if (k == matchPositions.size() || matchPositions[k] - matchPositions[k - 1] > kMaxGap) {
            clusters.push_back(make_pair((int32_t) clusterStart, (int32_t) (k - 1)));
            clusterStart = k;
        }
    }
    size_t bestCluster = 0;
    size_t bestSize = 0;
    for (size_t c = 0; c < clusters.size(); c++) {
        size_t sz = clusters[c].second - clusters[c].first + 1;
        if (sz > bestSize) { bestSize = sz; bestCluster = c; }
    }
    if (bestSize < kMinMatches) return make_pair(-1, -1);
    int32_t spanBegin = matchPositions[clusters[bestCluster].first];
    int32_t lastMatch = matchPositions[clusters[bestCluster].second];
    int32_t spanEnd = min(lastMatch + kTrailingBuffer, len);
    return make_pair(spanBegin, spanEnd);
}

bool TdTokenizer::hasSection(const set<UnicodeString>& sectionNames,
        const vector<UnicodeString>& sections) {
    bool ret = false;
    for (auto x : sections) if (sectionNames.find(x) != sectionNames.end()) return true;
    return ret;
}

void TdTokenizer::combineSectionAnnotations(CAS & cas,
        const set<UnicodeString>& sectionNames,
        const vector<UnicodeString>& sections,
        const vector<size_t>& b, const vector<size_t>& e,
        const UnicodeString type,
        AnnotationCounter ac) {
    FSIndexRepository & indexRep = cas.getIndexRepository();
    for (size_t i = 0; i < sections.size() - 1; i++) {
        if (sectionNames.find(sections[i]) != sectionNames.end())
            if (e[i] == b[i + 1]) {
                AnnotationFS fsSection = cas.createAnnotation(sectiontype_, b[i], e[i + 1]);
                fsSection.setStringValue(sectiontype_type_, type);
                fsSection.setStringValue(sectiontype_content_, sections[i + 1]);
                Feature faid = sectiontype_.getFeatureByBaseName("aid");
                if (faid.isValid()) fsSection.setIntValue(faid, ac.GetNextId());
                indexRep.addFS(fsSection);
            }
    }
}

std::string utf8Printable(const string & string) {
    int c, i;
    std::string ret("");
    int ix(string.length());
    for (i = 0; i < ix; i++) {
        c = (unsigned char) string[i];
        if (c == 0x09 || c == 0x0a || c == 0x0d || (0x20 <= c && c <= 0x7e)) // is_printable
            ret += string[i];
        else if (c == 0xc2) {
            if (i + 1 < ix)
                if (((unsigned char) string[i + 1]) == 0xb0) {
                    ret += " degree ";
                    i++;
                } else if (((unsigned char) string[i + 1]) == 0xb5) {
                    ret += " micro ";
                    i++;
                } else if (((unsigned char) string[i + 1]) == 0xb1) {
                    ret += " plus/minus ";
                    i++;
                } else if (((unsigned char) string[i + 1]) == 0xa9) {
                    ret += " copyright ";
                    i++;
                }
        } else if (c == 0xe2) {
            if (i + 2 < ix)
                if (((unsigned char) string[i + 1]) == 0x80)
                    if (((unsigned char) string[i + 2]) == 0x94) {
                        ret += "-";
                        i += 2;
                    }
        } else if (c == 0xef) {
            if (i + 2 < ix) {
                if (((unsigned char) string[i + 1]) == 0xac) {
                    if (((unsigned char) string[i + 2]) == 0x82)
                        ret += "fl";
                    if (((unsigned char) string[i + 2]) == 0x81)
                        ret += "fi";
                    if (((unsigned char) string[i + 2]) == 0x80)
                        ret += "ff";
                    i += 2;

                }
            }
        }
    }
    return ret;
}

TdTokenizer::TdTokenizer() {
    dlsetToken_ = set<UnicodeString >(
            tp_uima_globals::token_delimiters(),
            tp_uima_globals::token_delimiters() + G_initT_No);
    dlsetSentence_ = set<UnicodeString >(
            tp_uima_globals::sentence_delimiters(),
            tp_uima_globals::sentence_delimiters() + G_initS_No);
    disqSentence_.push_back("[\\(>\\s][A-Z]\\.[<\\s]$");
    const string part1 = "[\\(>\\s](Prof|Ph\\.D|Dr|[Ff]igs?|[Vv]ol|i\\.e|e\\.g";
    const string part2 = "|[Nn]o|[Vv]s|[Ee]x|al|ca)\\.[<\\s]$";
    disqSentence_.push_back(part1 + part2);
    maxfrontdisqcharlength_ = 4; // sniplet length in front of sentence delimiter
    maxbackdisqcharlength_ = 0; // sniplet length  following sentence delimiter.
    dlsetSection_.clear();
    for (auto x : tp_uima_globals::sectionArticleB()) dlsetSection_.insert(x);
    for (auto x : tp_uima_globals::sectionArticleE()) dlsetSection_.insert(x);
    for (auto x : tp_uima_globals::sectionAbstract()) dlsetSection_.insert(x);
    for (auto x : tp_uima_globals::sectionIntroduction()) dlsetSection_.insert(x);
    for (auto x : tp_uima_globals::sectionResult()) dlsetSection_.insert(x);
    for (auto x : tp_uima_globals::sectionDiscussion()) dlsetSection_.insert(x);
    for (auto x : tp_uima_globals::sectionConclusion()) dlsetSection_.insert(x);
    for (auto x : tp_uima_globals::sectionBackground()) dlsetSection_.insert(x);
    for (auto x : tp_uima_globals::sectionMaterialsMethods()) dlsetSection_.insert(x);
    for (auto x : tp_uima_globals::sectionDesign()) dlsetSection_.insert(x);
    for (auto x : tp_uima_globals::sectionAcknowledgments()) dlsetSection_.insert(x);
    for (auto x : tp_uima_globals::sectionReferences()) dlsetSection_.insert(x);
}

TdTokenizer::TdTokenizer(const TdTokenizer & orig) {
}

TdTokenizer::~TdTokenizer() {
}

TyErrorId TdTokenizer::initialize(AnnotatorContext & rclAnnotatorContext) {
    set<UnicodeString>::iterator it;
    trieToken_ = new TpTrie();
    for (it = dlsetToken_.begin(); it != dlsetToken_.end(); it++) {
        trieToken_->addWord(*it);
    }
    trieSentence_ = new TpTrie();
    for (it = dlsetSentence_.begin(); it != dlsetSentence_.end(); it++) {
        trieSentence_->addWord(*it);
    }
    trieSection_ = new TpTrie();
    for (it = dlsetSection_.begin(); it != dlsetSection_.end(); it++) {

        trieSection_->addWord(*it);
    }
    return (TyErrorId) UIMA_ERR_NONE;
}

TyErrorId TdTokenizer::typeSystemInit(TypeSystem const & crTypeSystem) {
    filenametype_ = crTypeSystem.getType("org.apache.uima.textpresso.filename");
    if (!filenametype_.isValid()) {
        getAnnotatorContext().getLogger().logError(
                "Error getting Type object for org.apache.uima.textpresso.filename.");
        cerr << "TdTokenizer::typeSystemInit - Error. See logfile." << endl;
        return (TyErrorId) UIMA_ERR_RESMGR_INVALID_RESOURCE;
    }
    filenametype_name_ = filenametype_.getFeatureByBaseName("value");
    rawsourcetype_ = crTypeSystem.getType("org.apache.uima.textpresso.rawsource");
    if (!rawsourcetype_.isValid()) {
        getAnnotatorContext().getLogger().logError(
                "Error getting Type object for org.apache.uima.textpresso.rawsource.");
        cerr << "TdTokenizer::typeSystemInit - Error. See logfile." << endl;
        return (TyErrorId) UIMA_ERR_RESMGR_INVALID_RESOURCE;
    }
    rawsourcetype_type_ = rawsourcetype_.getFeatureByBaseName("value");
    tokentype_ = crTypeSystem.getType("org.apache.uima.textpresso.token");
    if (!tokentype_.isValid()) {
        getAnnotatorContext().getLogger(). logError(
                "Error getting Type object for org.apache.uima.textpresso.token.");
        cerr << "TdTokenizer::typeSystemInit - Error. See logfile." << endl;
        return (TyErrorId) UIMA_ERR_RESMGR_INVALID_RESOURCE;
    }
    tokentype_content_ = tokentype_.getFeatureByBaseName("content");
    sentencetype_ = crTypeSystem.getType("org.apache.uima.textpresso.sentence");
    if (!sentencetype_.isValid()) {
        getAnnotatorContext().getLogger(). logError(
                "Error getting Type object for org.apache.uima.textpresso.sentence.");
        cerr << "TdTokenizer::typeSystemInit - Error. See logfile." << endl;
        return (TyErrorId) UIMA_ERR_RESMGR_INVALID_RESOURCE;
    }
    sentencetype_content_ = sentencetype_.getFeatureByBaseName("content");
    tpfnvhashtype_ =
            crTypeSystem.getType("org.apache.uima.textpresso.tpfnvhash");
    if (!tpfnvhashtype_.isValid()) {
        getAnnotatorContext().getLogger().logError(
                "Error getting Type object for org.apache.uima.textpresso.tpfnvhash.");
        cerr << "TdTokenizer::typeSystemInit - Error. See logfile." << endl;
        return (TyErrorId) UIMA_ERR_RESMGR_INVALID_RESOURCE;
    }
    tpfnvhashtype_content_ = tpfnvhashtype_.getFeatureByBaseName("content");
    pagetype_ = crTypeSystem.getType("org.apache.uima.textpresso.page");
    if (!pagetype_.isValid()) {
        getAnnotatorContext().getLogger().logError(
                "Error getting Type object for org.apache.uima.textpresso.page.");
        cerr << "TdTokenizer::typeSystemInit - Error. See logfile." << endl;
        return (TyErrorId) UIMA_ERR_RESMGR_INVALID_RESOURCE;
    }
    pagetype_value_ = pagetype_.getFeatureByBaseName("value");
    dblbrktype_ = crTypeSystem.getType("org.apache.uima.textpresso.dblbrk");
    if (!dblbrktype_.isValid()) {
        getAnnotatorContext().getLogger().logError(
                "Error getting Type object for org.apache.uima.textpresso.dblbrk.");
        cerr << "TdTokenizer::typeSystemInit - Error. See logfile." << endl;
        return (TyErrorId) UIMA_ERR_RESMGR_INVALID_RESOURCE;
    }
    rawsectiontype_ =
            crTypeSystem.getType("org.apache.uima.textpresso.rawsection");
    if (!rawsectiontype_.isValid()) {
        getAnnotatorContext().getLogger().logError(
                "Error getting Type object for org.apache.uima.textpresso.rawsection.");
        cerr << "TdTokenizer::typeSystemInit - Error. See logfile." << endl;
        return (TyErrorId) UIMA_ERR_RESMGR_INVALID_RESOURCE;
    }
    rawsectiontype_content_ = rawsectiontype_.getFeatureByBaseName("content");

    sectiontype_ =
            crTypeSystem.getType("org.apache.uima.textpresso.section");
    if (!sectiontype_.isValid()) {
        getAnnotatorContext().getLogger().logError(
                "Error getting Type object for org.apache.uima.textpresso.section.");
        cerr << "TdTokenizer::typeSystemInit - Error. See logfile." << endl;
        return (TyErrorId) UIMA_ERR_RESMGR_INVALID_RESOURCE;
    }
    sectiontype_content_ = sectiontype_.getFeatureByBaseName("content");
    sectiontype_type_ = sectiontype_.getFeatureByBaseName("type");
    imagetype_ =
            crTypeSystem.getType("org.apache.uima.textpresso.image");
    if (!imagetype_.isValid()) {
        getAnnotatorContext().getLogger().logError(
                "Error getting Type object for org.apache.uima.textpresso.image.");
        cerr << "TdTokenizer::typeSystemInit - Error. See logfile." << endl;
        return (TyErrorId) UIMA_ERR_RESMGR_INVALID_RESOURCE;
    }
    imagetype_filename_ = imagetype_.getFeatureByBaseName("filename");
    imagetype_page_ = imagetype_.getFeatureByBaseName("page");

    return (TyErrorId) UIMA_ERR_NONE;
}

TyErrorId TdTokenizer::destroy() {

    return (TyErrorId) UIMA_ERR_NONE;
}

TyErrorId TdTokenizer::process(CAS & tcas, ResultSpecification const & crResultSpecification) {
    AnnotationCounter ac(tcas);
    UnicodeStringRef usprelimref = tcas.getDocumentText();
    int32_t firsthash = usprelimref.indexOf('#', 0);
    UnicodeString numberstring;
    usprelimref.extract(0, firsthash, numberstring);
    stringstream auxstream;
    int32_t result;
    auxstream << numberstring;
    auxstream >> result;
    UnicodeString filename;
    usprelimref.extract(firsthash + 1, result - firsthash - 2, filename);
    UnicodeString usaux;
    usprelimref.extract(result, usprelimref.length() - result, usaux);

    string dummy;
    string f(usaux.toUTF8String<string >(dummy));

    textAndImageManager taim = textAndImageManager(path(f).parent_path());
    taim.loadImageFilenames();
    taim.loadTextFilenames();
    taim.loadTextfiles();
    string doc("\nBeginning of Article\n");
    vector<int> pageLengths;
    for (auto x : taim.textFile()) {
        std::string s(utf8Printable(x.second));
        doc += s;
        int len = 0;
        // for utf8 encoding, characters can be encoded with more than 1 byte.
        for (int i = 0; i != s.length(); i++)
            len += (x.second[i] & 0xc0) != 0x80;
        pageLengths.push_back(len);
    }
    doc += "\nEnd of Article\n";
    UnicodeString ustrInputText;
    ustrInputText.append(UnicodeString::fromUTF8(StringPiece(doc)));
    UnicodeStringRef usdocref(ustrInputText);
    tcas.setDocumentText(usdocref);
    getAnnotatorContext().getLogger().logMessage("process called");
    UnicodeString dst;
    usdocref.extract(0, usdocref.length(), dst);

    vector< pair<int32_t, int32_t> > p = trieToken_->searchAllWords(dst);
    sort(p.begin(), p.end()); // just to make sure it is sorted.
    WriteOutAnnotations(tcas, usdocref, p, tokentype_, tokentype_content_, ac, true);
    p.clear();

    p = trieSentence_->searchAllWords(dst);
    p = RemoveDelimiters(usdocref, disqSentence_, p,
            maxfrontdisqcharlength_, maxbackdisqcharlength_);
    sort(p.begin(), p.end());
    WriteOutAnnotations(tcas, usdocref, p, sentencetype_, sentencetype_content_, ac, false);
    p.clear();

    vector<int32_t> sectionPosMap;
    UnicodeString dstForSections = CleanPdfTagsForSectionSearch(dst, sectionPosMap);
    p = trieSection_->searchAllWords(dstForSections);
    for (auto & match : p) {
        match.first = sectionPosMap[match.first];
        match.second = sectionPosMap[match.second];
    }
    sort(p.begin(), p.end()); // just to make sure it is sorted.
    WriteOutAnnotations(tcas, usdocref, p, rawsectiontype_, rawsectiontype_content_, ac, true);
    p.clear();

    ANIndex allannindex = tcas.getAnnotationIndex();
    ANIterator aait = allannindex.iterator();
    aait.moveToFirst();
    vector<UnicodeString> sections;
    vector<size_t> sectionsB;
    vector<size_t> sectionsE;
    while (aait.isValid()) {
        Type currentType = aait.get().getType();
        string annType = currentType.getName().asUTF8();
        if (annType == "org.apache.uima.textpresso.rawsection") {
            sectionsB.push_back(aait.get().getBeginPosition());
            sectionsE.push_back(aait.get().getEndPosition());
            Feature f = currentType.getFeatureByBaseName("content");
            sections.push_back(aait.get().getStringValue(f).getBuffer());
        }
        aait.moveToNext();
    }

    bool hasResult(hasSection(tp_uima_globals::sectionResult(), sections));
    bool hasIntroduction(hasSection(tp_uima_globals::sectionIntroduction(), sections));
    bool hasBackground(hasSection(tp_uima_globals::sectionBackground(), sections));
    bool hasDiscussion(hasSection(tp_uima_globals::sectionDiscussion(), sections));
    bool hasConclusion(hasSection(tp_uima_globals::sectionConclusion(), sections));
    bool hasMM(hasSection(tp_uima_globals::sectionMaterialsMethods(), sections));
    bool hasDesign(hasSection(tp_uima_globals::sectionDesign(), sections));
    bool hasReferences(hasSection(tp_uima_globals::sectionReferences(), sections));
    // 2026-08-14: fall back to detecting a heading-less numbered reference
    // list (see DetectImplicitReferencesSpan above) when the trie found no
    // "References"-family heading at all.
    pair<int32_t, int32_t> implicitRefSpan(-1, -1);
    if (!hasReferences) {
        pair<int32_t, int32_t> cleanedSpan = DetectImplicitReferencesSpan(dstForSections);
        if (cleanedSpan.first >= 0) {
            int32_t endIdx = min(cleanedSpan.second, (int32_t) sectionPosMap.size() - 1);
            implicitRefSpan = make_pair(sectionPosMap[cleanedSpan.first], sectionPosMap[endIdx]);
            hasReferences = true;
        }
    }
    int score(0);
    if (hasIntroduction || hasBackground) score++;
    if (hasDiscussion || hasConclusion) score++;
    if (hasResult) score++;
    if (hasMM || hasDesign) score++;
    if (hasReferences) score++;
    // Threshold lowered 2026-08-14: >3 (4-of-5 categories) suppressed
    // section detection for 65% of a sampled 81-paper zero-section set
    // (score 2-3, one/two categories short), even when categories that
    // did match (typically references + one other) were correct. >1
    // still requires 2 independently-matched categories, guarding against
    // a single spurious isolated-line match, while recovering the
    // majority of legitimately-structured papers the old threshold blocked.
    if (score > 1) {
        combineSectionAnnotations(tcas, tp_uima_globals::sectionArticleB(), sections,
                sectionsB, sectionsE, "beginning of article", ac);
        combineSectionAnnotations(tcas, tp_uima_globals::sectionArticleE(), sections,
                sectionsB, sectionsE, "end of article", ac);
        combineSectionAnnotations(tcas, tp_uima_globals::sectionAbstract(), sections,
                sectionsB, sectionsE, "abstract", ac);
        combineSectionAnnotations(tcas, tp_uima_globals::sectionIntroduction(), sections,
                sectionsB, sectionsE, "introduction", ac);
        combineSectionAnnotations(tcas, tp_uima_globals::sectionResult(), sections,
                sectionsB, sectionsE, "result", ac);
        combineSectionAnnotations(tcas, tp_uima_globals::sectionDiscussion(), sections,
                sectionsB, sectionsE, "discussion", ac);
        combineSectionAnnotations(tcas, tp_uima_globals::sectionConclusion(), sections,
                sectionsB, sectionsE, "conclusion", ac);
        combineSectionAnnotations(tcas, tp_uima_globals::sectionBackground(), sections,
                sectionsB, sectionsE, "background", ac);
        combineSectionAnnotations(tcas, tp_uima_globals::sectionMaterialsMethods(), sections,
                sectionsB, sectionsE, "materials and methods", ac);
        combineSectionAnnotations(tcas, tp_uima_globals::sectionDesign(), sections,
                sectionsB, sectionsE, "design", ac);
        combineSectionAnnotations(tcas, tp_uima_globals::sectionAcknowledgments(), sections,
                sectionsB, sectionsE, "acknowledgments", ac);
        combineSectionAnnotations(tcas, tp_uima_globals::sectionReferences(), sections,
                sectionsB, sectionsE, "references", ac);
        if (implicitRefSpan.first >= 0 && implicitRefSpan.second > implicitRefSpan.first) {
            FSIndexRepository & indexRepImplicit = tcas.getIndexRepository();
            AnnotationFS fsImplicitRef = tcas.createAnnotation(sectiontype_,
                    implicitRefSpan.first, implicitRefSpan.second);
            fsImplicitRef.setStringValue(sectiontype_type_, "references");
            fsImplicitRef.setStringValue(sectiontype_content_,
                    UnicodeString("(implicit: numbered-list reference block, no heading text found)"));
            Feature faidImplicit = sectiontype_.getFeatureByBaseName("aid");
            if (faidImplicit.isValid()) fsImplicitRef.setIntValue(faidImplicit, ac.GetNextId());
            indexRepImplicit.addFS(fsImplicitRef);
        }
    }
    FSIndexRepository & indexRep = tcas.getIndexRepository();
    AnnotationFS fsNewTok = tcas.createAnnotation(tpfnvhashtype_, 0, usdocref.length());
    string shex = tpfnv(usdocref);
    UnicodeString ushex(shex.c_str());
    fsNewTok.setStringValue(tpfnvhashtype_content_, ushex);
    indexRep.addFS(fsNewTok);
    AnnotationFS fsNT2 = tcas.createAnnotation(rawsourcetype_, 0, usdocref.length());
    fsNT2.setStringValue(rawsourcetype_type_, "tai"); // stands for text and image
    // (the new pdftotext system)
    indexRep.addFS(fsNT2);
    AnnotationFS fsNT3 = tcas.createAnnotation(filenametype_, 0, usdocref.length());
    fsNT3.setStringValue(filenametype_name_, filename);
    indexRep.addFS(fsNT3);
    int b(0);
    std::map<int, std::pair<size_t, size_t>> pageBE;
    for (int i = 0; i != pageLengths.size(); i++) {
        AnnotationFS fsPage = tcas.createAnnotation(pagetype_, b, b + pageLengths[i]);
        // store page B and E for image annotation below
        pageBE.insert(std::make_pair<int, std::pair<size_t, size_t >>
                (i + 1, std::make_pair<size_t, size_t>(b, b + pageLengths[i])));
        fsPage.setIntValue(pagetype_value_, i + 1);
        b += pageLengths[i];
        Feature faid = pagetype_.getFeatureByBaseName("aid");
        if (faid.isValid())
            fsPage.setIntValue(faid, ac.GetNextId());
        indexRep.addFS(fsPage);
    }
    for (auto x : taim.imageFilenames()) {
        path p(x);
        string s(p.stem().stem().extension().string());
        int pagenumber(stoi(s.substr(1, s.size() - 1)));
        std::pair<size_t, size_t> auxpair(pageBE[pagenumber]);
        AnnotationFS fsImage = tcas.createAnnotation(imagetype_, auxpair.first, auxpair.second);
        fsImage.setIntValue(imagetype_page_, pagenumber);
        fsImage.setStringValue(imagetype_filename_, UnicodeString(x.c_str()));
        Feature faid = imagetype_.getFeatureByBaseName("aid");
        if (faid.isValid())
            fsImage.setIntValue(faid, ac.GetNextId());
        indexRep.addFS(fsImage);
    }
    size_t found(0);
    while (found < std::string::npos) {
        size_t pos = found + 1;
        found = doc.find("\n\n", pos);
        AnnotationFS fsPage = tcas.createAnnotation(dblbrktype_, found, found + 2);
        Feature faid = dblbrktype_.getFeatureByBaseName("aid");
        if (faid.isValid())
            fsPage.setIntValue(faid, ac.GetNextId());
        indexRep.addFS(fsPage);
    }
    Type rawsection = tcas.getTypeSystem().getType("org.apache.uima.textpresso.rawsection");
    ANIndex rawsectionindex = tcas.getAnnotationIndex(rawsection);
    ANIterator aait2 = rawsectionindex.iterator();
    aait2.moveToFirst();
    std::vector<AnnotationFS> removeList;
    while (aait2.isValid()) {
        removeList.push_back(aait2.get());
        aait2.moveToNext();
    }
    while (!removeList.empty()) {
        indexRep.removeFS(removeList.back());
        removeList.pop_back();
    }
    return (TyErrorId) UIMA_ERR_NONE;
}

MAKE_AE(TdTokenizer);
