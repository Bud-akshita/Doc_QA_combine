import React, { useState, useEffect } from "react";
import { X, AlertTriangle, Eye, Loader2 } from "lucide-react";
import { getBackendUrl } from "../utils/getBackendUrl";

const RiskModal = ({
  show,
  onClose,
  riskData,
  loadingRisk,
  onViewReference,
  token,
  filename,
}) => {
  const [API_BASE_URL, setApiBaseUrl] = useState("");
  const [expandedRisks, setExpandedRisks] = useState(new Set());
  const [loadingReferences, setLoadingReferences] = useState(new Set());

  // Fetch backend URL on mount
  useEffect(() => {
    const fetchUrl = async () => {
      try {
        const url = await getBackendUrl();
        setApiBaseUrl(url);
      } catch (error) {
        console.error("Failed to fetch backend URL:", error);
      }
    };

    fetchUrl();
  }, []);

  if (!show) return null;
  const toggleRiskExpansion = (index) => {
    setExpandedRisks((prev) => {
      const newExpanded = new Set(prev); 
      if (newExpanded.has(index)) {
        newExpanded.delete(index);
      } else {
        newExpanded.add(index);
      }
      return newExpanded;
    });
  };

  const handleViewReference = async (refId, riskIndex) => {
    setLoadingReferences((prev) => new Set(prev).add(`${riskIndex}-${refId}`));

    try {
      const response = await fetch(
        `${API_BASE_URL}/documents/get-reference/${encodeURIComponent(filename)}/${encodeURIComponent(refId)}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        const data = await response.json();
        onViewReference(data.reference_info, refId);
      } else {
        console.error("Failed to fetch reference");
      }
    } catch (error) {
      console.error("Error fetching reference:", error);
    } finally {
      setLoadingReferences((prev) => {
        const newSet = new Set(prev);
        newSet.delete(`${riskIndex}-${refId}`);
        return newSet;
      });
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content risk-modal">
        <div className="modal-header">
          <h3>
            <AlertTriangle className="risk-icon" />
            High Risk Clauses Analysis
          </h3>
          <button onClick={onClose} className="close-button">
            <X />
          </button>
        </div>

        <div className="modal-body">
          {loadingRisk ? (
            <div className="loading-state">
              <Loader2 className="loading-spinner spinning" />
              <p>Finding risks...</p>
            </div>
          ) : riskData && riskData.high_risk_clauses ? (
            <div className="risk-results">
              {riskData.high_risk_clauses.length === 0 ? (
                <div className="no-risks">
                  <AlertTriangle className="no-risk-icon" />
                  <p>No high-risk clauses detected in this document.</p>
                </div>
              ) : (
                <div className="risks-list">
                  <p className="risks-count">
                    Found {riskData.high_risk_clauses.length} high-risk
                    clause(s):
                  </p>
                  {riskData.high_risk_clauses.map((risk, index) => (
                    <div key={index} className="risk-item">
                      <div className="risk-header">
                        <div className="risk-title">
                          <div className="risk-title-left">
                            <AlertTriangle className="risk-warning-icon" />
                            <span>Risk Clause #{index + 1}</span>
                          </div>
                          <div className="title-references">
                            {risk.REF ? (
                              <button
                                className="title-reference-button"
                                onClick={() =>
                                  handleViewReference(risk.REF, index)
                                } // Pass hidden REF to backend
                                disabled={loadingReferences.has(
                                  `${index}-${risk.REF}`
                                )}
                              >
                                {loadingReferences.has(
                                  `${index}-${risk.REF}`
                                ) ? (
                                  <Loader2 className="button-spinner spinning" />
                                ) : (
                                  <Eye className="reference-icon" />
                                )}
                                View Reference
                              </button>
                            ) : (
                              <button
                                className="title-reference-button"
                                disabled
                              >
                                No Reference
                              </button>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="risk-details">
                        <div className="risk-content">
                          <p>
                            <strong>Clause:</strong>
                          </p>
                          <div className="clause-text">
                            {risk.clause || risk.text || "Risk clause content"}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="error-state">
              <AlertTriangle className="error-icon" />
              <p>Failed to analyze document for risks. Please try again.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RiskModal;
