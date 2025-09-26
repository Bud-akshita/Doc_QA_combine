import React from "react";
import { X, FileText, MapPin } from "lucide-react";

const ReferenceModal = ({ 
  show, 
  onClose, 
  referenceData,
  referenceId 
}) => {
  if (!show || !referenceData) return null;

  return (
    <div className="reference-overlay">
      <div className="modal-content reference-modal">
        <div className="modal-header">
          <h3>
            <FileText className="reference-icon" />
            Reference Details
          </h3>
          <button onClick={onClose} className="close-button">
            <X />
          </button>
        </div>

        <div className="modal-body">
          <div className="reference-details">
            {referenceData.page_number && (
              <div className="reference-meta">
                <MapPin className="meta-icon" />
                <span>Page {referenceData.page_number}</span>
              </div>
            )}
            
            <div className="reference-content">
              <h4>Content:</h4>
              <div className="content-text">
                {referenceData.chunk_text || referenceData.content || referenceData.text}
              </div>
            </div>

            {referenceData.metadata && (
              <div className="reference-metadata">
                <h4>Additional Information:</h4>
                <div className="metadata-content">
                  {Object.entries(referenceData.metadata).map(([key, value]) => (
                    <div key={key} className="metadata-item">
                      <strong>{key}:</strong> {value}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReferenceModal;