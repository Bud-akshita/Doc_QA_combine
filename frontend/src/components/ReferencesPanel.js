import React from "react";
import { X, FileText, Hash } from "lucide-react";

const ReferencesPanel = ({
  isOpen,
  onClose,
  references,
  currentConversationId,
  className = ""
}) => {
  if (!isOpen || !references || !currentConversationId) return null;

  const currentReferences = references[currentConversationId] || {};

  return (
    <div 
      className={`references-panel ${className}`}
      onClick={(e) => e.stopPropagation()} // Prevent backdrop clicks when clicking inside panel
    >
      <div className="references-header">
        <h3>
          <FileText size={20} className="section-icon" />
          References
        </h3>
        <button onClick={onClose} className="references-close-button">
          <X className="close-icon" />
        </button>
      </div>
      
      <div className="references-content">
        {Object.keys(currentReferences).length === 0 ? (
          <div className="no-references">
            <FileText size={48} className="empty-icon" />
            <p>No references available for this answer.</p>
          </div>
        ) : (
          <div className="references-list">
            <div className="references-info">
              <p>Showing references for this answer. Click any reference number in the text to jump to it.</p>
            </div>
            
            {Object.entries(currentReferences).map(([refId, refData]) => (
              <div key={refId} id={`ref-${refId}`} className="reference-item">
                <div className="reference-header">
                  <div className="reference-id">
                    <Hash size={16} />
                    Reference {refId}
                  </div>
                  {refData && refData.length >= 2 && (
                    <span className="page-number">
                      Page {refData[1]}
                    </span>
                  )}
                </div>
                
                <div className="reference-content">
                  {refData && refData.length >= 1 ? (
                    <>
                      <div className="reference-chunk">
                        <strong>Content:</strong>
                        <p style={{ whiteSpace: 'pre-wrap', textAlign: 'left' }}>{refData[0] || "No content available"}</p>
                      </div>
                      
                      {/* Removed redundant page meta section */}
                      
                      {refData.length > 2 && (
                        <div className="reference-additional">
                          <strong>Additional info:</strong>
                          <pre>{JSON.stringify(refData.slice(2), null, 2)}</pre>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="reference-empty">
                      No reference data available
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ReferencesPanel;