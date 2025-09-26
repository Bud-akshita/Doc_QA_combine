import React from "react";
import { History, X, ChevronDown, ChevronUp, MessageCircle } from "lucide-react";
import { formatDate, truncateText } from "../utils/formatUtils";

const HistoryModal = ({
  show,
  onClose,
  chatHistory,
  selectedDocument,
  expandedHistoryItems,
  onToggleHistoryItem
}) => {
  if (!show) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>
            <History className="section-icon" />
            Chat History for {selectedDocument}
          </h2>
          <button onClick={onClose} className="modal-close-button">
            <X className="close-icon" />
          </button>
        </div>

        <div className="modal-body">
          {chatHistory.length === 0 ? (
            <div className="empty-history">
              <MessageCircle className="empty-icon" />
              <p>No chat history found for {selectedDocument}</p>
              <p className="empty-subtitle">
                Start asking questions to build your chat history
              </p>
            </div>
          ) : (
            <div className="history-list">
              {chatHistory.map((item) => (
                <div key={item.id} className="history-item">
                  <div className="history-header">
                    <div className="history-meta">
                      <span className="history-date">
                        {formatDate(item.created_at)}
                      </span>
                    </div>
                    <button
                      onClick={() => onToggleHistoryItem(item.id)}
                      className="expand-button"
                    >
                      {expandedHistoryItems.has(item.id) ? (
                        <ChevronUp className="expand-icon" />
                      ) : (
                        <ChevronDown className="expand-icon" />
                      )}
                    </button>
                  </div>

                  <div className="history-preview">
                    <div className="history-question">
                      <strong>Q:</strong> {truncateText(item.question)}
                    </div>
                    {expandedHistoryItems.has(item.id) && (
                      <div className="history-answer">
                        <strong>A:</strong> {item.answer}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default HistoryModal;