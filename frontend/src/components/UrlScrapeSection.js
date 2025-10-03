import React, { useState , useEffect} from "react";
import { Globe, Download, Loader2, AlertCircle } from "lucide-react";
import { getBackendUrl } from "../utils/getBackendUrl";

const UrlScrapeSection = ({ token, onScrapeSuccess, message, setMessage }) => {
  const [API_BASE_URL, setApiBaseUrl] = useState("");
  const [url, setUrl] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // Fetch backend URL when component mounts
  useEffect(() => {
    const fetchUrl = async () => {
      try {
        const url = await getBackendUrl();
        setApiBaseUrl(url);
      } catch (error) {
        console.error("Failed to fetch backend URL:", error);
        setMessage({ text: "Backend URL not available", type: "error" });
      }
    };

    fetchUrl();
  }, [setMessage]);

  const handleScrapeUrl = async (e) => {
    e.preventDefault();

    if (!API_BASE_URL) {
      setMessage({ text: "Backend URL not loaded yet", type: "error" });
      return;
    }

    if (!url.trim()) {
      setMessage({ text: "Please enter a URL", type: "error" });
      return;
    }

    // Basic URL validation
    const urlPattern = /^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w \.-]*)*\/?$/;
    if (!urlPattern.test(url.trim())) {
      setMessage({ text: "Please enter a valid URL", type: "error" });
      return;
    }

    setIsLoading(true);
    setMessage({ text: "", type: "" });

    try {
      const response = await fetch(
        `${API_BASE_URL}/website/scrape?url=${encodeURIComponent(url.trim())}`,
        {
          method: "GET",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (response.ok) {
        // Extract filename from Content-Disposition header first
        const contentDisposition = response.headers.get("Content-Disposition");
        let filename = null;

        if (contentDisposition) {
          const patterns = [
            /filename\*=UTF-8''([^;]+)/,
            /filename="([^"]+)"/,
            /filename=([^;]+)/
          ];

          for (const pattern of patterns) {
            const match = contentDisposition.match(pattern);
            if (match) {
              filename = decodeURIComponent(match[1]);
              break;
            }
          }
        }

        if (!filename) {
          try {
            const urlObj = new URL(url.startsWith("http") ? url : `https://${url}`);
            const domain = urlObj.hostname.replace("www.", "").split(".")[0];
            filename = `${domain}.pdf`;
          } catch (error) {
            filename = `website_${Date.now()}.pdf`;
            console.warn("Could not parse URL for filename:", error);
          }
        }

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = downloadUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(downloadUrl);

        setMessage({
          text: `Website data gathered and converted to PDF successfully! File: ${filename}`,
          type: "success",
        });

        setUrl(""); // Clear input

        if (onScrapeSuccess) onScrapeSuccess();
      } else {
        const errorData = await response.json().catch(() => ({}));
        const errorMessage = errorData.detail || "Failed to get data from website";
        setMessage({ text: errorMessage, type: "error" });
      }
    } catch (error) {
      console.error("Scrape error:", error);
      setMessage({
        text: "Network error. Please check your connection and try again.",
        type: "error",
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="url-scrape-section">
      <div className="section-header">
        <Globe className="section-icon" />
        <h3>Get Data From Website</h3>
      </div>
      
      <form onSubmit={handleScrapeUrl} className="url-scrape-form">
        <div className="url-input-group">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Enter website URL (e.g., https://example.com/)"
            className="url-input"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !url.trim()}
            className="scrape-button"
          >
            {isLoading ? (
              <>
                <Loader2 className="button-icon spinning" />
                Getting Data...
              </>
            ) : (
              <>
                <Download className="button-icon" />
                Get Data & Download
              </>
            )}
          </button>
        </div>
      </form>

      {message.text && (
        <div className={`message ${message.type}`}>
          {message.type === "error" && <AlertCircle className="message-icon" />}
          <span>{message.text}</span>
        </div>
      )}

      <div className="scrape-info">
        <h4>How it works:</h4>
        <ul>
          <li>The PDF with website data will be automatically downloaded and added to your documents</li>
          <li>You can then ask questions about the website content</li>
        </ul>
      </div>
    </div>
  );
};

export default UrlScrapeSection;