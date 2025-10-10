import React, { useState, useEffect, useCallback } from "react";
import { useTimedMessage } from "./hooks/useTimedMessage";
import DocumentSidebar from "./components/DocumentSidebar";
import UploadSection from "./components/UploadSection";
import UrlScrapeSection from "./components/UrlScrapeSection";
import QASection from "./components/QASection";
import HistoryModal from "./components/HistoryModal";
import SummaryModal from "./components/SummaryModal";
import ReferencesPanel from "./components/ReferencesPanel";
import RiskModal from "./components/riskmodal";
import ReferenceModal from "./components/referencemodal";
import SmartReminder from "./components/SmartReminder";
import "./docs.css";
import { getBackendUrl } from "./utils/getBackendUrl";

const DocumentManager = ({ token, onLogout }) => {
  // Existing state management
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedDocuments, setSelectedDocuments] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [chatHistory, setChatHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [summaries, setSummaries] = useState({});
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const [currentSummary, setCurrentSummary] = useState(null);
  const [expandedHistoryItems, setExpandedHistoryItems] = useState(new Set());
  const [references, setReferences] = useState({});
  const [showReferencesPanel, setShowReferencesPanel] = useState(false);
  const [currentReferenceConversationId, setCurrentReferenceConversationId] = useState(null);

  // Updated high-risk functionality state
  const [riskData, setRiskData] = useState(null);
  const [loadingRisk, setLoadingRisk] = useState(false);
  const [showRiskModal, setShowRiskModal] = useState(false);
  const [showReferenceModal, setShowReferenceModal] = useState(false);
  const [currentReferenceData, setCurrentReferenceData] = useState(null);
  const [currentReferenceId, setCurrentReferenceId] = useState(null);

  // NEW: Risk processing status tracking
  const [riskProcessingStatus, setRiskProcessingStatus] = useState({});
  const [riskPollingIntervals, setRiskPollingIntervals] = useState({});

  // Smart Reminder state
  const [showSmartReminderModal, setShowSmartReminderModal] = useState(false);
  const [loadingReminder, setLoadingReminder] = useState(false);

  // Existing message hooks
  const [message, setMessage] = useTimedMessage({ text: "", type: "" });
  const [qaMessage, setQaMessage] = useTimedMessage({ text: "", type: "" });
  const [summaryMessage, setSummaryMessage] = useTimedMessage({ text: "", type: "" });
  const [scrapeMessage, setScrapeMessage] = useTimedMessage({ text: "", type: "" });
  const [riskMessage, setRiskMessage] = useTimedMessage({ text: "", type: "" });
  const [API_BASE_URL, setApiBaseUrl] = useState("");

  useEffect(() => {
    const fetchUrl = async () => {
      try {
        const url = await getBackendUrl();
        setApiBaseUrl(url);
      } catch (error) {
        console.error("Failed to get backend URL:", error);
      }
    };
    fetchUrl();
  }, []);

  // NEW: Start high-risk analysis in background
  const startHighRiskAnalysis = async (docName, docType) => {
    try {
      const formData = new FormData();
      formData.append("filename", docName);
      formData.append("doc_type", docType);

      const response = await fetch(`${API_BASE_URL}/documents/high-risk-start`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (response.ok) {
        setRiskProcessingStatus(prev => ({ ...prev, [docName]: "processing" }));
        startRiskPolling(docName, docType); // pass docType here
        console.log(`High risk analysis started for ${docName}`);
        return true;
      }
    } catch (error) {
      console.error("Error starting high risk analysis:", error);
      return false;
    }
  };

  // NEW: Poll for risk analysis results
  const startRiskPolling = (docName, docType) => {
    if (riskPollingIntervals[docName]) {
      clearInterval(riskPollingIntervals[docName]);
    }

    const intervalId = setInterval(async () => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/documents/high-risk-result/${encodeURIComponent(docName)}?doc_type=${encodeURIComponent(docType)}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );

        if (response.ok) {
          const data = await response.json();

          if (data.status === "done") {
            setRiskProcessingStatus(prev => ({ ...prev, [docName]: "done" }));
            clearInterval(intervalId);
            setRiskPollingIntervals(prev => {
              const newIntervals = { ...prev };
              delete newIntervals[docName];
              return newIntervals;
            });
            console.log(`High risk analysis completed for ${docName}`);
          }
        }
      } catch (error) {
        console.error("Error polling for risk results:", error);
      }
    }, 5000);

    setRiskPollingIntervals(prev => ({ ...prev, [docName]: intervalId }));
  };

  // NEW: Get risk analysis results
  const getRiskAnalysisResults = async (docName) => {
    setLoadingRisk(true);
    setRiskData(null);
    setShowRiskModal(true);

    try {
      const response = await fetch(
        `${API_BASE_URL}/documents/high-risk-result/${encodeURIComponent(docName)}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (response.ok) {
        const data = await response.json();

        if (data.status === "done") {
          setRiskData({ high_risk_clauses: data.high_risk_clauses });
          setRiskMessage({
            text: "Risk analysis results loaded successfully!",
            type: "success",
          });
        } else {
          setRiskMessage({
            text: "Risk analysis is still processing. Please wait...",
            type: "info",
          });
        }
      } else {
        setRiskMessage({
          text: "Failed to get risk analysis results",
          type: "error",
        });
      }
    } catch (error) {
      setRiskMessage({
        text: "Network error while getting risk analysis results",
        type: "error",
      });
      console.error("Error getting risk results:", error);
    } finally {
      setLoadingRisk(false);
    }
  };

  // Updated document selection handler
  const handleDocumentSelect = async (docName, isChecked) => {
    if (isChecked) {
      setSelectedDocuments((prev) => [...prev, docName]);

      // Check if risk analysis hasn't been started for this document
      if (!riskProcessingStatus[docName]) {
        const selectedDoc = documents.find((doc) => doc.doc_name === docName);
        if (selectedDoc) {
          // Start background risk analysis
          const started = await startHighRiskAnalysis(docName, selectedDoc.doc_type);
          if (!started) {
            console.warn(`Failed to start risk analysis for ${docName}`);
          }
        }
      }
    } else {
      setSelectedDocuments((prev) => prev.filter((name) => name !== docName));
    }
  };

  // Updated find high-risk clauses function
  const findHighRiskClauses = async () => {
    if (selectedDocuments.length === 0) {
      setRiskMessage({
        text: "Please select at least one document to analyze for risks",
        type: "error",
      });
      return;
    }

    const documentName = selectedDocuments[0];
    const status = riskProcessingStatus[documentName];

    if (status === "processing") {
      setRiskMessage({
        text: "Risk analysis is still in progress. Please wait...",
        type: "info",
      });
      return;
    }

    if (status === "done") {
      // Get the results
      await getRiskAnalysisResults(documentName);
    } else {
      // Start the analysis if not started
      const selectedDoc = documents.find((doc) => doc.doc_name === documentName);
      if (selectedDoc) {
        const started = await startHighRiskAnalysis(documentName, selectedDoc.doc_type);
        if (started) {
          setRiskMessage({
            text: "Risk analysis started. This may take a few minutes...",
            type: "info",
          });
        } else {
          setRiskMessage({
            text: "Failed to start risk analysis",
            type: "error",
          });
        }
      }
    }
  };

  // Handle delete document (updated to clear risk status)
  const handleDeleteDocument = async (docName, docType) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/documents/delete?doc_name=${encodeURIComponent(
          docName
        )}&doc_type=${encodeURIComponent(docType)}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        setMessage({
          text: `Document "${docName}" deleted successfully`,
          type: "success",
        });

        // Remove from selected documents if it was selected
        setSelectedDocuments((prev) => prev.filter((name) => name !== docName));

        // Clear risk processing status and stop polling
        if (riskPollingIntervals[docName]) {
          clearInterval(riskPollingIntervals[docName]);
        }
        setRiskProcessingStatus(prev => {
          const newStatus = { ...prev };
          delete newStatus[docName];
          return newStatus;
        });
        setRiskPollingIntervals(prev => {
          const newIntervals = { ...prev };
          delete newIntervals[docName];
          return newIntervals;
        });

        // Refresh the document list
        fetchDocuments();
      } else {
        const errorData = await response.json();
        setMessage({
          text: errorData.detail || "Failed to delete document",
          type: "error",
        });
      }
    } catch (error) {
      setMessage({
        text: "Network error while deleting document",
        type: "error",
      });
      console.error("Error deleting document:", error);
    }
  };

  // Cleanup polling intervals on unmount
  useEffect(() => {
    return () => {
      Object.values(riskPollingIntervals).forEach(intervalId => {
        clearInterval(intervalId);
      });
    };
  }, [riskPollingIntervals]);

  // Existing functions (keeping all the original functions)
  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/documents/`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
        cache: "no-store",
      });

      if (res.ok) {
        const data = await res.json();
        setDocuments(Array.isArray(data) ? data : []);
      } else {
        setDocuments([]);
        setMessage({ text: "Failed to load documents", type: "error" });
      }
    } catch (err) {
      console.error("Error fetching docs:", err);
      setDocuments([]);
      setMessage({ text: "Network error loading documents", type: "error" });
    } finally {
      setLoading(false);
    }
  }, [API_BASE_URL, token, setMessage]);

  const handleAskQuestion = async (questionText) => {
    if (!questionText.trim()) {
      setQaMessage({ text: "Please enter a question", type: "error" });
      return;
    }

    if (selectedDocuments.length === 0) {
      setQaMessage({
        text: "Please select at least one document",
        type: "error",
      });
      return;
    }

    const selectedDocumentName = selectedDocuments[0];
    const selectedDoc = documents.find(
      (doc) => doc.doc_name === selectedDocumentName
    );

    if (!selectedDoc) {
      setQaMessage({
        text: "Selected document not found",
        type: "error",
      });
      return;
    }

    const newConversation = {
      id: Date.now(),
      question: questionText,
      answer: "",
      loading: true,
    };

    setConversations((prev) => [...prev, newConversation]);
    setQaMessage({ text: "", type: "" });

    try {
      const formData = new FormData();
      formData.append("filename", selectedDocumentName);
      formData.append("document_type", selectedDoc.doc_type);
      formData.append("question", questionText);

      const response = await fetch(`${API_BASE_URL}/documents/ask-question`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();

        setConversations((prev) =>
          prev.map((conv) =>
            conv.id === newConversation.id
              ? {
                ...conv,
                answer: data.answer,
                loading: false,
                references: data.ref_map,
              }
              : conv
          )
        );

        if (data.ref_map) {
          console.log(
            "Setting references for conversation",
            newConversation.id,
            ":",
            data.ref_map
          );
          setReferences((prev) => ({
            ...prev,
            [newConversation.id]: data.ref_map,
          }));
        }

        setQaMessage({
          text: "Question answered successfully!",
          type: "success",
        });
      } else {
        const errorData = await response.json();
        const errorMessage = errorData.detail || "Failed to get answer";

        setConversations((prev) =>
          prev.map((conv) =>
            conv.id === newConversation.id
              ? { ...conv, answer: `Error: ${errorMessage}`, loading: false }
              : conv
          )
        );

        setQaMessage({ text: errorMessage, type: "error" });
      }
    } catch (error) {
      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === newConversation.id
            ? {
              ...conv,
              answer: "Network error. Please try again.",
              loading: false,
            }
            : conv
        )
      );

      setQaMessage({ text: "Network error. Please try again.", type: "error" });
      console.error("Ask question error:", error);
    }
  };

  const handleShowSmartReminder = () => {
    if (selectedDocuments.length === 0) {
      setMessage({
        text: "Please select at least one document to view smart reminders",
        type: "error",
      });
      return;
    }

    setShowSmartReminderModal(true);
    setLoadingReminder(false);
  };

  const handleViewReferenceFromRisk = (referenceData, referenceId) => {
    console.log("Reference Data:", referenceData);
    console.log("Reference ID:", referenceId);

    setCurrentReferenceData(referenceData);
    setCurrentReferenceId(referenceId);
    setShowReferenceModal(true);
  };

  // ... (keep all other existing functions like fetchChatHistory, generateSummary, etc.)
  const fetchChatHistory = async () => {
    if (selectedDocuments.length === 0) {
      setMessage({
        text: "Please select at least one document to view history",
        type: "error",
      });
      return;
    }

    setLoadingHistory(true);
    try {
      const documentName = selectedDocuments[0];
      const response = await fetch(
        `${API_BASE_URL}/documents/history/${encodeURIComponent(documentName)}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (response.ok) {
        const data = await response.json();
        setChatHistory(Array.isArray(data) ? data : []);
        setShowHistoryModal(true);
      } else if (response.status === 404) {
        setChatHistory([]);
        setShowHistoryModal(true);
      } else {
        const errorData = await response.json();
        setMessage({
          text: errorData.detail || "Failed to fetch chat history",
          type: "error",
        });
      }
    } catch (error) {
      setMessage({
        text: "Network error while fetching chat history",
        type: "error",
      });
      console.error("Error fetching chat history:", error);
    } finally {
      setLoadingHistory(false);
    }
  };

  const generateSummary = async () => {
    if (selectedDocuments.length === 0) {
      setMessage({
        text: "Please select at least one document to generate summary",
        type: "error",
      });
      return;
    }

    const documentName = selectedDocuments[0];

    if (summaries[documentName]) {
      setCurrentSummary({
        document: documentName,
        summary: summaries[documentName],
      });
      setShowSummaryModal(true);
      return;
    }

    setCurrentSummary({ document: documentName, summary: null });
    setShowSummaryModal(true);
    setLoadingSummary(true);
    setSummaryMessage({ text: "", type: "" });

    try {
      const selectedDoc = documents.find(
        (doc) => doc.doc_name === documentName
      );
      if (!selectedDoc) {
        setSummaryMessage({
          text: "Selected document not found",
          type: "error",
        });
        setLoadingSummary(false);
        return;
      }

      const formData = new FormData();
      formData.append("filename", documentName);
      formData.append("document_type", selectedDoc.doc_type);

      const response = await fetch(`${API_BASE_URL}/documents/summary`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();

        setSummaries((prev) => ({ ...prev, [documentName]: data.summary }));
        setCurrentSummary({ document: documentName, summary: data.summary });

        setSummaryMessage({
          text: "Summary generated successfully!",
          type: "success",
        });
      } else {
        const errorData = await response.json();
        setSummaryMessage({
          text: errorData.detail || "Failed to generate summary",
          type: "error",
        });
        console.error("Summary generation error:", errorData);
      }
    } catch (error) {
      setSummaryMessage({
        text: "Network error while generating summary",
        type: "error",
      });
      console.error("Error generating summary:", error);
    } finally {
      setLoadingSummary(false);
    }
  };

  const toggleHistoryItem = (id) => {
    setExpandedHistoryItems((prev) => {
      const newExpanded = new Set(prev);
      if (newExpanded.has(id)) {
        newExpanded.delete(id);
      } else {
        newExpanded.add(id);
      }
      return newExpanded;
    });
  };

  const handleShowReferences = (conversationId) => {
    console.log("handleShowReferences called with:", conversationId);
    console.log("Available references:", references);
    console.log("References for conversation:", references[conversationId]);

    setCurrentReferenceConversationId(conversationId);
    setShowReferencesPanel(true);

    setTimeout(() => {
      console.log("State after setting:", {
        showReferencesPanel: true,
        currentReferenceConversationId: conversationId,
      });
    }, 100);
  };

  const handleCloseReferences = () => {
    console.log("handleCloseReferences called");
    setShowReferencesPanel(false);
    setCurrentReferenceConversationId(null);
  };

  const handleScrapeSuccess = () => {
    fetchDocuments();
  };

  useEffect(() => {
    if (token) {
      fetchDocuments();
    }
  }, [token, fetchDocuments]);

  useEffect(() => {
    console.log("ReferencesPanel state changed:", {
      showReferencesPanel,
      currentReferenceConversationId,
      hasReferences: Object.keys(references).length > 0,
      referencesData: references,
    });
  }, [showReferencesPanel, currentReferenceConversationId, references]);

  return (
    <div className="document-manager">
      <DocumentSidebar
        documents={documents}
        loading={loading}
        selectedDocuments={selectedDocuments}
        onDocumentSelect={handleDocumentSelect}
        onGenerateSummary={generateSummary}
        onFetchChatHistory={fetchChatHistory}
        onRefreshDocuments={fetchDocuments}
        onFindHighRisk={findHighRiskClauses}
        onShowSmartReminder={handleShowSmartReminder}
        onDeleteDocument={handleDeleteDocument}
        onLogout={onLogout}
        loadingSummary={loadingSummary}
        loadingHistory={loadingHistory}
        loadingRisk={loadingRisk}
        loadingReminder={loadingReminder}
        riskProcessingStatus={riskProcessingStatus} // NEW PROP
      />
      <div className="document-main">
        <UploadSection
          token={token}
          API_BASE_URL={API_BASE_URL}
          onUploadSuccess={fetchDocuments}
          message={message}
          setMessage={setMessage}
        />

        <UrlScrapeSection
          token={token}
          API_BASE_URL={API_BASE_URL}
          onScrapeSuccess={handleScrapeSuccess}
          message={scrapeMessage}
          setMessage={setScrapeMessage}
        />

        <QASection
          selectedDocuments={selectedDocuments}
          conversations={conversations}
          qaMessage={qaMessage}
          references={references}
          onAskQuestion={handleAskQuestion}
          onShowReferences={handleShowReferences}
        />
      </div>

      {/* Existing Modals */}
      <HistoryModal
        show={showHistoryModal}
        onClose={() => setShowHistoryModal(false)}
        chatHistory={chatHistory}
        selectedDocument={selectedDocuments[0]}
        expandedHistoryItems={expandedHistoryItems}
        onToggleHistoryItem={toggleHistoryItem}
      />

      <SummaryModal
        show={showSummaryModal}
        onClose={() => setShowSummaryModal(false)}
        currentSummary={currentSummary}
        summaryMessage={summaryMessage}
        setSummaryMessage={setSummaryMessage}
        onRegenerateSummary={generateSummary}
        summaries={summaries}
        setSummaries={setSummaries}
        loadingSummary={loadingSummary}
      />

      <RiskModal
        show={showRiskModal}
        onClose={() => setShowRiskModal(false)}
        riskData={riskData}
        loadingRisk={loadingRisk}
        onViewReference={handleViewReferenceFromRisk}
        token={token}
        API_BASE_URL={API_BASE_URL}
        filename={selectedDocuments[0]}
      />

      <ReferenceModal
        show={showReferenceModal}
        onClose={() => setShowReferenceModal(false)}
        referenceData={currentReferenceData}
        referenceId={currentReferenceId}
      />

      {/* Smart Reminder Modal */}
      <SmartReminder
        show={showSmartReminderModal}
        onClose={() => setShowSmartReminderModal(false)}
        selectedDocument={selectedDocuments[0]}
        documents={documents}
        token={token}
        API_BASE_URL={API_BASE_URL}
      />

      {/* References Panel Backdrop */}
      <div
        className={`references-backdrop ${showReferencesPanel ? "open" : ""}`}
        onClick={(e) => {
          e.stopPropagation();
          handleCloseReferences();
        }}
      />

      {/* References Panel */}
      <ReferencesPanel
        isOpen={showReferencesPanel}
        onClose={handleCloseReferences}
        references={references}
        currentConversationId={currentReferenceConversationId}
        className={showReferencesPanel ? "open" : ""}
      />
    </div>
  );
};

export default DocumentManager;