import React from "react";
import { File, History, RefreshCw, AlertTriangle, Bell, Trash2 } from "lucide-react";
import { formatDate } from "../utils/formatUtils";

const DocumentSidebar = ({
  documents,
  loading,
  selectedDocuments,
  onDocumentSelect,
  onGenerateSummary,
  onFetchChatHistory,
  onRefreshDocuments,
  onFindHighRisk, // New prop
  onShowSmartReminder, // New prop for smart reminder
  onDeleteDocument, // New prop for delete functionality
  onLogout,
  loadingSummary,
  loadingHistory,
  loadingRisk, // New prop
  loadingReminder, // New prop for reminder loading
  riskProcessingStatus // New prop to show processing status
}) => {
  const handleDeleteDocument = (docName, docType) => {
    if (window.confirm(`Are you sure you want to delete "${docName}"?`)) {
      onDeleteDocument(docName, docType);
    }
  };

  // Helper function to get risk button status
  const getRiskButtonStatus = () => {
    if (selectedDocuments.length === 0) {
      return {
        disabled: true,
        title: "Select a document to find high risk clauses",
        showBadge: false,
        isProcessing: false
      };
    }

    const selectedDoc = selectedDocuments[0];
    const status = riskProcessingStatus[selectedDoc];

    if (status === "processing") {
      return {
        disabled: true,
        title: "Risk analysis in progress...",
        showBadge: true,
        isProcessing: true
      };
    }

    if (status === "done") {
      return {
        disabled: false,
        title: "View High Risk Analysis Results",
        showBadge: true,
        isProcessing: false
      };
    }

    return {
      disabled: false,
      title: "Find High Risk Clauses",
      showBadge: true,
      isProcessing: false
    };
  };

  const riskButtonStatus = getRiskButtonStatus();

  return (
    <div className="document-sidebar">
      <div className="sidebar-header">
        <h3>Your Documents</h3>
        <div className="header-actions">
          <button
            onClick={onGenerateSummary}
            disabled={loadingSummary || selectedDocuments.length === 0}
            className="summary-button"
            title={
              selectedDocuments.length === 0
                ? "Select a document to generate summary"
                : "Generate Summary"
            }
          >
            <File
              className={`summary-icon ${loadingSummary ? "spinning" : ""}`}
            />
            {selectedDocuments.length > 0 && (
              <span className="selected-badge">
                {selectedDocuments.length}
              </span>
            )}
          </button>

          <button
            onClick={onFetchChatHistory}
            disabled={loadingHistory || selectedDocuments.length === 0}
            className="history-button"
            title={
              selectedDocuments.length === 0
                ? "Select documents to view history"
                : "View Chat History"
            }
          >
            <History
              className={`history-icon ${loadingHistory ? "spinning" : ""}`}
            />
            {selectedDocuments.length > 0 && (
              <span className="selected-badge">
                {selectedDocuments.length}
              </span>
            )}
          </button>

          {/* New Smart Reminder Button */}
          <button
            onClick={onShowSmartReminder}
            disabled={loadingReminder || selectedDocuments.length === 0}
            className="reminder-button"
            title={
              selectedDocuments.length === 0
                ? "Select a document to view smart reminders"
                : "View Smart Reminders"
            }
          >
            <Bell
              className={`reminder-icon ${loadingReminder ? "spinning" : ""}`}
            />
            {selectedDocuments.length > 0 && (
              <span className="selected-badge">
                {selectedDocuments.length}
              </span>
            )}
          </button>

          {/* High Risk Button - Updated */}
          <button
            onClick={onFindHighRisk}
            disabled={riskButtonStatus.disabled || loadingRisk}
            className={`risk-button ${riskProcessingStatus[selectedDocuments[0]] === "processing" ? "processing" : ""}`}
            title={riskButtonStatus.title}
          >
            <AlertTriangle
              className={`risk-icon ${(loadingRisk || riskButtonStatus.isProcessing) ? "spinning" : ""}`}
            />
            {riskButtonStatus.showBadge && (
              <span className={`selected-badge ${riskProcessingStatus[selectedDocuments[0]] === "processing" ? "processing-badge" : ""}`}>
                {riskProcessingStatus[selectedDocuments[0]] === "processing" ? "⏳" : selectedDocuments.length}
              </span>
            )}
          </button>

          <button
            onClick={onRefreshDocuments}
            disabled={loading}
            className="refresh-button"
          >
            <RefreshCw
              className={`refresh-icon ${loading ? "spinning" : ""}`}
            />
          </button>
        </div>
      </div>

      <div className="document-list">
        {loading ? (
          <div className="loading-state">
            <div className="loading-spinner"></div>
            <p>Loading documents...</p>
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <File className="empty-icon" />
            <p>No documents yet</p>
            <p className="empty-subtitle">
              Upload your first document to get started
            </p>
          </div>
        ) : (
          documents.map((doc) => (
            <div key={doc.id} className="document-item">
              <div className="document-checkbox">
                <input
                  type="checkbox"
                  id={`doc-${doc.id}`}
                  checked={selectedDocuments.includes(doc.doc_name)}
                  onChange={(e) =>
                    onDocumentSelect(doc.doc_name, e.target.checked)
                  }
                  className="checkbox-input"
                />
                <label htmlFor={`doc-${doc.id}`} className="checkbox-label">
                  <div className="document-info">
                    <h4 className="document-name" title={doc.doc_name}>
                      {doc.doc_name}
                      {riskProcessingStatus[doc.doc_name] === "processing" && (
                        <span className="processing-indicator" title="Risk analysis in progress">
                          ⏳
                        </span>
                      )}
                      {riskProcessingStatus[doc.doc_name] === "done" && (
                        <span className="completed-indicator" title="Risk analysis completed">
                          ✅
                        </span>
                      )}
                    </h4>
                    <p className="document-meta">
                      {doc.doc_type} • {formatDate(doc.uploaded_at)}
                    </p>
                  </div>
                </label>
                <button
                  onClick={() => handleDeleteDocument(doc.doc_name, doc.doc_type)}
                  className="delete-button"
                  title={`Delete ${doc.doc_name}`}
                >
                  <Trash2 className="delete-icon" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="sidebar-footer">
        <button onClick={onLogout} className="logout-button">
          Logout
        </button>
      </div>
    </div>
  );
};

export default DocumentSidebar;