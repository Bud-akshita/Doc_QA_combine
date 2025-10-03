import React, { useEffect,useState, useRef } from "react";
import { Upload, X } from "lucide-react";
import { formatFileSize } from "../utils/formatUtils";
import { getBackendUrl } from "../utils/getBackendUrl";

const UploadSection = ({ token, onUploadSuccess, message, setMessage }) => {
  const [API_BASE_URL, setApiBaseUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [docType, setDocType] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

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

  const handleUpload = async () => {
    if (!selectedFile || !docType) {
      setMessage({
        text: "Please select a file and document type",
        type: "error",
      });
      return;
    }

    setUploading(true);
    setMessage({ text: "", type: "" });

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("doc_type", docType);

      const response = await fetch(`${API_BASE_URL}/documents/upload`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (response.ok) {
        await response.json();
        setMessage({ text: "File uploaded successfully!", type: "success" });
        setSelectedFile(null);
        setDocType("");
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
        onUploadSuccess();
      } else {
        const errorData = await response.json();
        setMessage({
          text: errorData.detail || "Upload failed",
          type: "error",
        });
      }
    } catch (error) {
      setMessage({ text: "Network error. Please try again.", type: "error" });
      console.log(error);
    } finally {
      setUploading(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      setSelectedFile(file);
      setDocType("");
    }
  };

  const clearSelection = () => {
    setSelectedFile(null);
    setDocType("");
    document.getElementById("file-input").value = "";
  };

  return (
    <div className="upload-section">
      <h2>Upload Document</h2>

      {message.text && (
        <div className={`message ${message.type}`}>{message.text}</div>
      )}

      <div
        className={`upload-area ${dragOver ? "drag-over" : ""} ${selectedFile ? "has-file" : ""
          }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {selectedFile ? (
          <div className="selected-file">
            <div className="file-preview">
              <div className="file-details">
                <h4>{selectedFile.name}</h4>
                <p>{formatFileSize(selectedFile.size)}</p>
                <p>Type: {docType}</p>
              </div>
              <button onClick={clearSelection} className="clear-button">
                <X className="clear-icon" />
              </button>
            </div>
          </div>
        ) : (
          <>
            <Upload className="upload-icon" />
            <h3>Drop your file here</h3>
            <p>or click to browse</p>
            <input
              type="file"
              id="file-input"
              className="file-input"
              accept="*/*"
              ref={fileInputRef}
              onChange={(e) => {
                if (e.target.files.length > 0) {
                  setSelectedFile(e.target.files[0]);
                  setDocType("");
                }
              }}
            />
          </>
        )}
      </div>

      {selectedFile && (
        <div className="upload-controls">
          <div className="form-group">
            <label htmlFor="doc-type">Document Type:</label>
            <select
              id="doc-type"
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              className="doc-type-select"
            >
              <option value="">Select document type</option>
              <option value="loan">Loan Documents</option>
              <option value="insurance">Insurance Documents</option>
              <option value="tenders">Tenders</option>
              <option value="credit_card_terms">Credit Card Terms</option>
              <option value="other">Other</option>
            </select>
          </div>

          <button
            onClick={handleUpload}
            disabled={uploading || !docType}
            className="upload-button"
          >
            {uploading ? (
              <>
                <div className="loading-spinner"></div>
                Uploading...
              </>
            ) : (
              <>
                <Upload className="button-icon" />
                Upload File
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
};

export default UploadSection;