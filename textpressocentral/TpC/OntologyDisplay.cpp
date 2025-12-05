/* 
 * File:   OntologyDisplay.cpp
 * Author: mueller
 * 
 * Created on July 17, 2017, 2:48 PM
 */

#include <Wt/WContainerWidget>
#include "TextpressoCentralGlobalDefinitions.h"
#include "OntologyDisplay.h"
#include "PgList.h"
#include <Wt/WScrollArea>
#include <Wt/WBreak>
#include <Wt/WCssDecorationStyle>
#include <Wt/WComboBox>
#include <Wt/WAnchor>
#include <Wt/WLink>
#include <boost/algorithm/string/predicate.hpp>
#include <boost/algorithm/string/replace.hpp>
#include <thread>
#include <sstream>
#include <ctime>
#include <pqxx/pqxx>

#define CELLHEIGHT 2
//#define CELLWIDTH 20
#define MAXENTRIES 5000

namespace {

    std::vector<std::string> GetAllSubTables(std::string stem) {
        std::vector<std::string> ret;
        ret.clear();
        pqxx::connection cn(PGONTOLOGY);
        pqxx::work w(cn);
        pqxx::result r;
        std::stringstream pc;
        pc << "select tablename from pg_tables where tablename like '";
        pc << stem << "_%" << "'";
        r = w.exec(pc.str());
        for (pqxx::result::size_type i = 0; i != r.size(); i++) {
            std::string name;
            if (r[i]["tablename"].to(name))
                ret.push_back(name);
        }
        w.commit();
        cn.disconnect();
        return ret;
    }
}

OntologyDisplay::OntologyDisplay(PickCategoryContainer *pcc,
        OntologyTermQuery *otc, Wt::WLength h, Wt::WContainerWidget *parent)
: Wt::WContainerWidget(parent) {
    // Download links container (shown above filter when category is selected)
    dlc_ = new Wt::WContainerWidget();
    dlc_->hide();
    addWidget(dlc_);
    // Filter container
    ftc_ = new Wt::WContainerWidget();
    ftc_->hide();
    Wt::WText * ftlabel = new Wt::WText("Filter: ");
    ftcolname_ = new Wt::WComboBox();
    PgList * allowed = new PgList(PGONTOLOGYBROWSER, PGONTOLOGYBROWSWERCOLUMNS);
    if (!allowed->HasList()) {
        std::set<std::string> defaults;
        defaults.insert("eid");
        defaults.insert("term");
        defaults.insert("category");
        allowed->SaveList(defaults);
    }
    for (auto colname : allowed->GetList())
        ftcolname_->addItem((Wt::WString(colname)));
    delete allowed;
    ftvalue_ = new Wt::WLineEdit();
    ftlabel->setInline(true);
    ftcolname_->setInline(true);
    ftvalue_->setInline(true);
    ftc_->addWidget(ftlabel);
    ftc_->addWidget(ftcolname_);
    ftc_->addWidget(ftvalue_);
    addWidget(ftc_);
    Wt::WScrollArea * cs = new Wt::WScrollArea();
    cs->setHeight(h);
    cs->setScrollBarPolicy(Wt::WScrollArea::ScrollBarAsNeeded);
    addWidget(cs);
    csc_ = new Wt::WContainerWidget();
    cs->setWidget(csc_);
    pcc->OkClicked().connect(boost::bind(&OntologyDisplay::SelectionOkClicked, this, pcc));
    otc->TermEntered().connect(boost::bind(&OntologyDisplay::SearchTermEntered, this, otc));
}

OntologyDisplay::OntologyDisplay(const OntologyDisplay& orig) {
}

OntologyDisplay::~OntologyDisplay() {
}

void OntologyDisplay::SelectionOkClicked(PickCategoryContainer *pcc) {
    PopulateTable(pcc, "", "");
    ftvalue_->setText("");
    ftc_->show();
    ftvalue_->enterPressed().connect(std::bind([ = ](){
        PopulateTable(pcc, ftcolname_->currentText().toUTF8(),
        ftvalue_->text().toUTF8());
    }));

    // Generate download links for selected category (including subcategories)
    dlc_->clear();
    dlc_->hide();
    std::set<Wt::WString> selectedWithChildren(pcc->GetSelected(true));  // true = include children
    std::set<Wt::WString> selectedOnly(pcc->GetSelected(false));  // false = just the selected node
    if (!selectedOnly.empty()) {
        std::string mainCat = selectedOnly.begin()->toUTF8();  // The main selected category name

        // Query all ontology members and search for entries in all selected categories
        std::vector<TpOntEntry*> entries;
        PgList ontmembers(PGONTOLOGY, ONTOLOGYMEMBERSTABLENAME);
        for (const auto& cat : selectedWithChildren) {
            std::string catStr = cat.toUTF8();
            for (const auto& ont : ontmembers.GetList()) {
                std::vector<std::string> st(GetAllSubTables(
                        PGONTOLOGYTABLENAME + std::string("_") + ont));
                for (const auto& xst : st) {
                    TpOntApi * toa = new TpOntApi(
                            xst,
                            PCRELATIONSTABLENAME + std::string("_") + ont,
                            PADCRELATIONSTABLENAME + std::string("_") + ont);
                    toa->SearchDbString(TpOntApi::category, catStr);
                    for (auto entry : toa->GetResultList()) {
                        entries.push_back(new TpOntEntry(*entry));
                    }
                    delete toa;
                }
            }
        }

        if (!entries.empty()) {
            // Generate OBO content
            std::string oboContent = GenerateOboContent(mainCat, entries);
            std::string headerContent = GenerateHeaderContent(mainCat);

            // Create safe filename from category
            std::string safeCat = mainCat;
            boost::replace_all(safeCat, " ", "_");
            boost::replace_all(safeCat, "(", "");
            boost::replace_all(safeCat, ")", "");
            boost::replace_all(safeCat, "/", "_");

            // Create download link for OBO file
            Wt::WMemoryResource * oboResource = new Wt::WMemoryResource("text/plain");
            oboResource->setData(std::vector<unsigned char>(oboContent.begin(), oboContent.end()));
            oboResource->suggestFileName(safeCat + ".obo");
            Wt::WAnchor * oboAnchor = new Wt::WAnchor(Wt::WLink(oboResource), "Download OBO file");
            oboAnchor->setTarget(Wt::TargetNewWindow);

            // Create download link for header file
            Wt::WMemoryResource * headerResource = new Wt::WMemoryResource("text/plain");
            headerResource->setData(std::vector<unsigned char>(headerContent.begin(), headerContent.end()));
            headerResource->suggestFileName(safeCat + ".headerobo");
            Wt::WAnchor * headerAnchor = new Wt::WAnchor(Wt::WLink(headerResource), "Download header file");
            headerAnchor->setTarget(Wt::TargetNewWindow);

            dlc_->addWidget(oboAnchor);
            dlc_->addWidget(new Wt::WText(" | "));
            dlc_->addWidget(headerAnchor);
            dlc_->show();
        }

        // Clean up entries
        for (auto entry : entries) {
            delete entry;
        }
    }
}

void OntologyDisplay::SearchTermEntered(OntologyTermQuery *otc) {
    dlc_->hide();
    ftc_->hide();
    csc_->clear();
    statusline_ = new Wt::WText();
    csc_->addWidget(statusline_);
    std::string where = "where term ~ '\\m" + (otc->GetTerm()).toUTF8() + "\\M'";
    PgList ontmembers(PGONTOLOGY, ONTOLOGYMEMBERSTABLENAME);
    if (!ontmembers.GetList().empty()) {
        std::string ont(*ontmembers.GetList().begin());
        TpOntApi * toa = new TpOntApi(
                PGONTOLOGYTABLENAME + std::string("_") + ont + std::string("_0"),
                PCRELATIONSTABLENAME + std::string("_") + ont,
                PADCRELATIONSTABLENAME + std::string("_") + ont);
        std::vector<std::string> headers(toa->GetColumnHeaders());
        delete toa;
        Wt::WStandardItemModel * model = new Wt::WStandardItemModel(0, 0);
        Wt::WTableView * table(CreateTableHeader(model, headers));
        int resultcount(0);
        std::vector<TpOntApi*> toa_vec;
        toa_vec.clear();
        std::vector<std::thread*> thread_vec;
        thread_vec.clear();
        for (auto ovar : ontmembers.GetList())
            if (resultcount < MAXENTRIES) {
                std::vector<std::string> st(GetAllSubTables(
                        PGONTOLOGYTABLENAME + std::string("_") + ovar));
                for (auto xst : st) {
                    toa_vec.push_back(new TpOntApi(
                            xst,
                            PCRELATIONSTABLENAME + std::string("_") + ovar,
                            PADCRELATIONSTABLENAME + std::string("_") + ovar));
                    thread_vec.push_back(new std::thread([ = ](TpOntApi * toa){
                        toa->DeleteAllResults();
                        toa->SearchDbWithWhereClause(where);
                    }, toa_vec.back()));
                    if (thread_vec.size() > 25)
                        while (thread_vec.size() > 0) {
                            thread_vec.back()->join();
                            delete thread_vec.back();
                            thread_vec.pop_back();
                            resultcount += toa_vec.back()->GetResultListSize();
                            AddToModel(model, toa_vec.back()->GetResultList(), "", "");
                            delete toa_vec.back();
                            toa_vec.pop_back();
                        }
                }
            }
        while (!thread_vec.empty()) {
            thread_vec.back()->join();
            delete thread_vec.back();
            thread_vec.pop_back();
            resultcount += toa_vec.back()->GetResultListSize();
            AddToModel(model, toa_vec.back()->GetResultList(), "", "");
            delete toa_vec.back();
            toa_vec.pop_back();
        }
        csc_->addWidget(table);
    }
}

void OntologyDisplay::PopulateTable(PickCategoryContainer *pcc,
        std::string ftcolname, std::string ftvalue) {
    csc_->clear();
    statusline_ = new Wt::WText();
    csc_->addWidget(statusline_);
    std::set<Wt::WString> selected(pcc->GetSelected(true));
    PgList ontmembers(PGONTOLOGY, ONTOLOGYMEMBERSTABLENAME);
    if (!ontmembers.GetList().empty()) {
        std::string ont(*ontmembers.GetList().begin());
        TpOntApi * toa = new TpOntApi(
                PGONTOLOGYTABLENAME + std::string("_") + ont + std::string("_0"),
                PCRELATIONSTABLENAME + std::string("_") + ont,
                PADCRELATIONSTABLENAME + std::string("_") + ont);
        std::vector<std::string> headers(toa->GetColumnHeaders());
        delete toa;
        Wt::WStandardItemModel * model = new Wt::WStandardItemModel(0, 0);
        Wt::WTableView * table(CreateTableHeader(model, headers));
        int resultcount(0);
        std::vector<TpOntApi*> toa_vec;
        toa_vec.clear();
        std::vector<std::thread*> thread_vec;
        thread_vec.clear();
        mmsstype cat2ont(pcc->GetTCB()->GetCat2Ont());
        for (auto cat : selected) {
            std::pair<mmsstype::iterator, mmsstype::iterator> catrange
                    = cat2ont.equal_range(cat.toUTF8());
            for (auto it = catrange.first; it != catrange.second; it++)
                if (resultcount < MAXENTRIES) {
                    std::vector<std::string> st(GetAllSubTables(
                            PGONTOLOGYTABLENAME + std::string("_") + (*it).second));
                    for (auto xst : st) {
                        toa_vec.push_back(new TpOntApi(
                                xst,
                                PCRELATIONSTABLENAME + std::string("_") + (*it).second,
                                PADCRELATIONSTABLENAME + std::string("_") + (*it).second));
                        thread_vec.push_back(new std::thread([ = ](TpOntApi * toa){
                            toa->DeleteAllResults();
                            toa->SearchDbString(TpOntApi::category, cat.toUTF8());
                        }, toa_vec.back()));
                        if (thread_vec.size() > 25)
                            while (thread_vec.size() > 0) {
                                thread_vec.back()->join();
                                delete thread_vec.back();
                                thread_vec.pop_back();
                                resultcount += toa_vec.back()->GetResultListSize();
                                AddToModel(model, toa_vec.back()->GetResultList(), ftcolname, ftvalue);
                                delete toa_vec.back();
                                toa_vec.pop_back();
                            }
                    }
                }
        }
        while (!thread_vec.empty()) {
            thread_vec.back()->join();
            delete thread_vec.back();
            thread_vec.pop_back();
            resultcount += toa_vec.back()->GetResultListSize();
            AddToModel(model, toa_vec.back()->GetResultList(), ftcolname, ftvalue);
            delete toa_vec.back();
            toa_vec.pop_back();
        }
        csc_->addWidget(table);
    }
}

Wt::WTableView * OntologyDisplay::CreateTableHeader(Wt::WStandardItemModel * model,
        const std::vector<std::string> & headers) {
    PgList * allowed = new PgList(PGONTOLOGYBROWSER, PGONTOLOGYBROWSWERCOLUMNS);
    std::vector<std::string> allowedheaders;
    for (auto colname : headers)
        if (allowed->IsInList(colname))
            allowedheaders.push_back(colname);
    delete allowed;
    Wt::WTableView * ret = new Wt::WTableView();
    ret->setSortingEnabled(true);
    ret->setAlternatingRowColors(true);
    ret->setRowHeight(Wt::WLength(CELLHEIGHT, Wt::WLength::FontEm));
    ret->decorationStyle().setBackgroundColor(Wt::WColor(200, 200, 255));
    ret->setColumnResizeEnabled(true);
    //
    if (allowedheaders.size() > 0) {
        model->insertColumns(0, allowedheaders.size());
        int col = 0;
        for (auto colname : allowedheaders)
            model->setHeaderData(col++, boost::any(colname));
    }
    ret->setModel(model);
    double tablewidth = 100.;
    double colwidth = tablewidth / double(model->columnCount());
    for (int i = 0; i < model->columnCount(); i++)
        ret->setColumnWidth(i, Wt::WLength(colwidth, Wt::WLength::FontEm));
    ret->setWidth(Wt::WLength(tablewidth, Wt::WLength::FontEm));
    return ret;
}

void OntologyDisplay::AddToModel(Wt::WStandardItemModel * model,
        std::vector<TpOntEntry*> items,
        std::string ftcolname, std::string ftvalue) {
    std::vector<TpOntEntry*> filtered;
    if (ftvalue.empty())
        filtered = items;
    else
        for (int r = 0; r < items.size(); r++) {
            std::string v(items[r]->
                    GetColumn(boost::any_cast<std::string>(ftcolname)));
            if (boost::starts_with(v, ftvalue)) filtered.push_back(items[r]);
        }
    if (model->rowCount() + filtered.size() > MAXENTRIES) {
        std::string taux;
        taux = "Table has more than "
                + std::to_string(MAXENTRIES) + " entries. "
                + "Please reduce your selection or use filter.";
        statusline_->setText(taux);
        statusline_->decorationStyle().setForegroundColor(Wt::red);
    }
    if (model->columnCount() > 0) {
        model->insertRows(0, std::min(int(filtered.size()), MAXENTRIES));
        for (int r = 0; r < std::min(int(filtered.size()), MAXENTRIES); r++)
            for (int c = 0; c < model->columnCount(); c++) {
                std::string s = filtered[r]->GetColumn(boost::any_cast<std::string>
                        (model->headerData(c)));
                model->setData(r, c, boost::any(s));
            }
    }

}

std::string OntologyDisplay::GenerateOboContent(const std::string& category,
        const std::vector<TpOntEntry*>& entries) {
    std::stringstream ss;

    // Generate OBO format content
    for (const auto& entry : entries) {
        ss << "[Term]\n";
        ss << "id: " << entry->GetEntryId() << "\n";
        ss << "name: " << entry->GetTerm() << "\n";
        if (!entry->GetCategory().empty()) {
            ss << "is_a: " << category << "\n";
        }
        if (!entry->GetDbXref().empty()) {
            ss << "xref: " << entry->GetDbXref() << "\n";
        }
        if (!entry->GetSource().empty()) {
            ss << "def: \"From " << entry->GetSource() << "\" []\n";
        }
        ss << "\n";
    }

    return ss.str();
}

std::string OntologyDisplay::GenerateHeaderContent(const std::string& category) {
    std::stringstream ss;

    // Get current date
    time_t now = time(0);
    struct tm* timeinfo = localtime(&now);
    char dateBuffer[80];
    strftime(dateBuffer, sizeof(dateBuffer), "%d:%m:%Y %H:%M", timeinfo);

    // Generate header in OBO format
    ss << "format-version: 1.2\n";
    ss << "data-version: " << dateBuffer << "\n";
    ss << "date: " << dateBuffer << "\n";
    ss << "saved-by: Textpresso\n";
    ss << "\n";
    ss << "[Term]\n";
    ss << "id: Tp:0000000\n";
    ss << "name: " << category << "\n";
    ss << "\n";

    return ss.str();
}
