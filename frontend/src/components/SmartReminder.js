import React, { useState, useEffect, useCallback, useRef } from "react";
import { getBackendUrl } from "../utils/getBackendUrl";
import {
  X,
  Bell,
  BellOff,
  Calendar,
  AlertCircle,
  CheckCircle,
  Mail,
  Clock,
  Trash2,
} from "lucide-react";

// useTimedMessage hook
const useTimedMessage = (initialState = { text: "", type: "" }) => {
  const [message, setMessage] = useState(initialState);
  const timeoutRef = useRef(null);

  const setTimedMessage = useCallback((newMessage) => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    setMessage(newMessage);

    if (newMessage.text) {
      timeoutRef.current = setTimeout(() => {
        setMessage({ text: "", type: "" });
      }, 3000); // 3 seconds for success message
    }
  }, []);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return [message, setTimedMessage];
};

const SmartReminder = ({
  show,
  onClose,
  selectedDocument,
  documents,
    token,
}) => {
  const [API_BASE_URL, setApiBaseUrl] = useState("");
  const [reminderData, setReminderData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setTimedMessage] = useTimedMessage();
  const [enabledReminders, setEnabledReminders] = useState(new Set());
  const [scheduledNotifications, setScheduledNotifications] = useState([]);
  const [globalNotificationDays, setGlobalNotificationDays] = useState(1);
  const [showDaysInput, setShowDaysInput] = useState(false);
  const [schedulingReminders, setSchedulingReminders] = useState(false);

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

  // Parse the reminder data from API response
  const parseReminderData = (dataString) => {
    if (!dataString) return [];

    const lines = dataString.split("\n").filter((line) => line.trim());
    const reminders = [];

    lines.forEach((line) => {
      // Match date pattern DD-MM-YYYY followed by description
      const match = line.match(/^-?\s*(\d{2}-\d{2}-\d{4})\s*-\s*(.+)$/);
      if (match) {
        const [, dateStr, description] = match;
        const [day, month, year] = dateStr.split("-");
        const date = new Date(year, month - 1, day);

        // Include all dates (past and future)
        const reminderId = `${dateStr}-${description.replace(/\s+/g, "-")}`;
        reminders.push({
          id: reminderId,
          date: dateStr,
          dateObj: date,
          description: description.trim(),
          enabled: false, // Default to disabled
        });
      }
    });

    // Sort by date
    return reminders.sort((a, b) => a.dateObj - b.dateObj);
  };

  // Schedule email notification
  const scheduleEmailNotification = async (reminder) => {
    try {
      const response = await fetch(`${API_BASE_URL}/documents/schedule-email`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          subject: reminder.description,
          date: reminder.date,
          days: globalNotificationDays,
        }),
      });

      if (response.ok) {
        const result = await response.json();
        console.log(result.task_id);
        return {
          success: true,
          taskId: result.task_id,
          scheduledFor: result.scheduled_for,
        };
      } else {
        const errorData = await response.json();
        throw new Error(errorData.message || "Failed to schedule email");
      }
    } catch (error) {
      console.error("Schedule email error:", error);
      return { success: false, error: error.message };
    }
  };

  // Cancel scheduled email notification (you'll need to implement this endpoint)
  const cancelEmailNotification = async (taskId) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/documents/cancel-email/${taskId}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (response.ok) {
        return { success: true };
      } else {
        return { success: false };
      }
    } catch (error) {
      console.error("Cancel email error:", error);
      return { success: false };
    }
  };

  // Toggle reminder enable/disable
  const toggleReminder = async (reminderId) => {
    const reminder = reminderData.find((r) => r.id === reminderId);
    if (!reminder) return;

    const isCurrentlyEnabled = enabledReminders.has(reminderId);

    if (isCurrentlyEnabled) {
      // Disable reminder - cancel scheduled notification
      const scheduledNotification = scheduledNotifications.find(
        (n) => n.reminderId === reminderId
      );

      if (scheduledNotification) {
        const cancelResult = await cancelEmailNotification(
          scheduledNotification.taskId
        );
        console.log(scheduledNotification.taskId);
        if (cancelResult.success) {
          // Remove from scheduled notifications
          setScheduledNotifications((prev) =>
            prev.filter((n) => n.reminderId !== reminderId)
          );
        }
      }

      // Remove from enabled reminders
      setEnabledReminders((prev) => {
        const newSet = new Set(prev);
        newSet.delete(reminderId);
        return newSet;
      });
    } else {
      // Enable reminder - schedule notification
      setSchedulingReminders(true);
      const scheduleResult = await scheduleEmailNotification(reminder);
      setSchedulingReminders(false);

      if (scheduleResult.success) {
        // Add to enabled reminders
        setEnabledReminders((prev) => {
          const newSet = new Set(prev);
          newSet.add(reminderId);
          return newSet;
        });

        // Add to scheduled notifications
        setScheduledNotifications((prev) => [
          ...prev,
          {
            reminderId,
            taskId: scheduleResult.taskId,
            scheduledFor: scheduleResult.scheduledFor,
            description: reminder.description,
            date: reminder.date,
            days: globalNotificationDays,
          },
        ]);

        setTimedMessage({
          text: `Email reminder scheduled for ${reminder.description}`,
          type: "success",
        });
      } else {
        setTimedMessage({
          text: `Failed to schedule reminder: ${scheduleResult.error}`,
          type: "error",
        });
      }
    }
  };

  // Update global notification days
  const updateGlobalNotificationDays = (days) => {
    const numDays = Math.max(1, Math.min(7, parseInt(days) || 1));
    setGlobalNotificationDays(numDays);
  };

  // Remove scheduled notification
  const removeScheduledNotification = async (notification) => {
    const cancelResult = await cancelEmailNotification(notification.taskId);
    if (cancelResult.success) {
      // Remove from scheduled notifications
      setScheduledNotifications((prev) =>
        prev.filter((n) => n.reminderId !== notification.reminderId)
      );

      // Remove from enabled reminders
      setEnabledReminders((prev) => {
        const newSet = new Set(prev);
        newSet.delete(notification.reminderId);
        return newSet;
      });

      setTimedMessage({
        text: "Scheduled notification cancelled",
        type: "success",
      });
    } else {
      setTimedMessage({
        text: "Failed to cancel notification",
        type: "error",
      });
    }
  };

  // Initialize enabled reminders when data is loaded (start with all disabled)
  useEffect(() => {
    if (reminderData) {
      const initialEnabled = new Set(); // Empty set - all disabled by default
      setEnabledReminders(initialEnabled);
      setScheduledNotifications([]); // Clear scheduled notifications when new data loads
    }
  }, [reminderData]);

  // Fetch smart reminders from API
  const fetchSmartReminders = async () => {
    if (!selectedDocument) {
      setTimedMessage({ text: "No document selected", type: "error" });
      return;
    }

    // Find the selected document to get its doc_type
    const selectedDoc = documents.find(
      (doc) => doc.doc_name === selectedDocument
    );
    if (!selectedDoc) {
      setTimedMessage({ text: "Selected document not found", type: "error" });
      return;
    }

    setLoading(true);
    setTimedMessage({ text: "", type: "" });
    setShowDaysInput(false);

    try {
      const formData = new FormData();
      formData.append("file", selectedDocument);
      formData.append("doc_type", selectedDoc.doc_type);

      const response = await fetch(`${API_BASE_URL}/documents/smart-reminder`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();

        // Handle different response formats
        if (result.status === "success" && result.data) {
          const parsedData = parseReminderData(result.data);
          setReminderData(parsedData);
          if (parsedData.length > 0) {
            setTimedMessage({
              text: `Found ${parsedData.length} reminders`,
              type: "success",
            });
            setTimeout(() => {
              setShowDaysInput(true);
            }, 1000);
          } else {
            setTimedMessage({
              text: "No reminder data found",
              type: "warning",
            });
          }
        } else if (typeof result === "string") {
          // Handle case where API returns string directly
          const parsedData = parseReminderData(result);
          setReminderData(parsedData);
          if (parsedData.length > 0) {
            setTimedMessage({
              text: `Found ${parsedData.length} reminders`,
              type: "success",
            });
            setTimeout(() => {
              setShowDaysInput(true);
            }, 1000);
          } else {
            setTimedMessage({
              text: "No reminder data found",
              type: "warning",
            });
          }
        } else {
          console.log("Unexpected API response format:", result);
          setTimedMessage({
            text: "Unexpected response format",
            type: "error",
          });
        }
      } else {
        const errorData = await response.json();
        // Handle validation errors
        let errorMessage = "Failed to fetch reminders";

        if (Array.isArray(errorData.detail)) {
          // Handle validation error array
          errorMessage = errorData.detail
            .map((err) => err.msg || err)
            .join(", ");
        } else if (typeof errorData.detail === "string") {
          errorMessage = errorData.detail;
        } else if (errorData.message) {
          errorMessage = errorData.message;
        }

        setTimedMessage({
          text: errorMessage,
          type: "error",
        });
      }
    } catch (error) {
      setTimedMessage({
        text: "Network error while fetching reminders",
        type: "error",
      });
      console.error("Smart reminder error:", error);
    } finally {
      setLoading(false);
    }
  };
  // Fetch reminders when modal opens
  useEffect(() => {
    if (show && selectedDocument) {
      setTimedMessage({ text: "", type: "" });
      setShowDaysInput(false);
      fetchSmartReminders();
    }
  }, [show, selectedDocument, setTimedMessage]);

  if (!show) return null;

  const enabledCount = reminderData
    ? reminderData.filter((r) => enabledReminders.has(r.id)).length
    : 0;

  return (
    <div className="modal-overlay">
      <div className="modal-content smart-reminder-modal">
        <div className="modal-header">
          <h3>
            <Bell className="modal-icon" />
            Smart Reminders
            {selectedDocument && (
              <span className="document-name"> - {selectedDocument}</span>
            )}
          </h3>
          <button onClick={onClose} className="close-button">
            <X />
          </button>
        </div>

        <div className="modal-body">
          {/* Scheduled Notifications Section */}
          {scheduledNotifications.length > 0 && (
            <div className="scheduled-notifications-section">
              <h4 className="scheduled-title">
                <Clock size={18} />
                Scheduled Email Notifications ({scheduledNotifications.length})
              </h4>
              <div className="scheduled-notifications-list">
                {scheduledNotifications.map((notification) => (
                  <div
                    key={notification.reminderId}
                    className="scheduled-notification"
                  >
                    <div className="notification-content">
                      <div className="notification-description">
                        <Mail size={14} />
                        {notification.description}
                      </div>
                      <div className="notification-details">
                        <span className="notification-date">
                          Event: {notification.date}
                        </span>
                        <span className="notification-timing">
                          Notify: {notification.days}{" "}
                          {notification.days === 0 ? "day" : "days"} before
                        </span>
                        <span className="scheduled-time">
                          Scheduled:{" "}
                          {notification.scheduledFor}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => removeScheduledNotification(notification)}
                      className="remove-notification-btn"
                      title="Cancel scheduled notification"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Message Display */}
          {message.text && (
            <div className={`message ${message.type}`}>
              {message.type === "success" && <CheckCircle size={16} />}
              {message.type === "error" && <AlertCircle size={16} />}
              {message.text}
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="loading-container">
              <div className="loading-spinner"></div>
              <p>Analyzing document for important dates...</p>
            </div>
          )}

          {/* Scheduling State */}
          {schedulingReminders && (
            <div className="scheduling-overlay">
              <div className="scheduling-spinner"></div>
              <p>Scheduling email reminder...</p>
            </div>
          )}

          {/* Days Input Section - Shows between success message and reminders */}
          {showDaysInput &&
            reminderData &&
            reminderData.length > 0 &&
            !loading && (
              <div className="days-input-section">
                <p>
                  How many days before each reminder would you like to receive
                  email notifications?
                </p>
                <div className="days-input-container">
                  <input
                    type="number"
                    min="1"
                    max="7"
                    value={globalNotificationDays}
                    onChange={(e) =>
                      updateGlobalNotificationDays(e.target.value)
                    }
                    className="days-input"
                  />
                  <span className="days-label">
                    {globalNotificationDays === 1 ? "day" : "days"} before
                  </span>
                </div>
              </div>
            )}

          {/* Reminders List */}
          {showDaysInput && reminderData && reminderData.length > 0 && (
            <div className="reminders-list">
              <div className="reminders-header">
                <h4>Select Reminders ({reminderData.length} found)</h4>
                <div className="header-info">
                  <span className="enabled-count">{enabledCount} selected</span>
                  <span className="notification-info">
                    • Email {globalNotificationDays}{" "}
                    {globalNotificationDays === 1 ? "day" : "days"} before
                  </span>
                </div>
              </div>
              {reminderData.map((reminder) => {
                const isEnabled = enabledReminders.has(reminder.id);
                const isScheduled = scheduledNotifications.some(
                  (n) => n.reminderId === reminder.id
                );
                return (
                  <div
                    key={reminder.id}
                    className={`reminder-item ${!isEnabled ? "disabled" : ""}`}
                  >
                    <button
                      className="reminder-bell-toggle"
                      onClick={() => toggleReminder(reminder.id)}
                      title={isEnabled ? "Disable reminder" : "Enable reminder"}
                      disabled={schedulingReminders}
                    >
                      {isEnabled ? (
                        <Bell size={18} className="bell-enabled" />
                      ) : (
                        <BellOff size={18} className="bell-disabled" />
                      )}
                    </button>
                    <div className="reminder-content">
                      <div className="reminder-description">
                        {reminder.description}
                        <div className="reminder-status">
                          <span
                            className={`notification-status ${
                              isEnabled ? "on" : "off"
                            }`}
                          >
                            {isEnabled ? "ON" : "OFF"}
                          </span>
                          {isScheduled && (
                            <span className="scheduled-badge">
                              <Mail size={12} />
                              SCHEDULED
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="reminder-date">
                        <Calendar size={14} />
                        {reminder.date}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Empty State */}
          {!loading && reminderData && reminderData.length === 0 && (
            <div className="empty-reminders">
              <Calendar className="empty-icon" />
              <h4>No reminders found</h4>
              <p>This document doesn't contain any dates or reminders.</p>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <div className="footer-right">
            <button
              onClick={fetchSmartReminders}
              disabled={loading}
              className="refresh-btn"
            >
              Refresh Reminders
            </button>
            <button onClick={onClose} className="close-btn">
              Close
            </button>
          </div>
        </div>
      </div>

      <style jsx>{`
        .smart-reminder-modal {
          max-width: 700px;
          max-height: 80vh;
          overflow-y: auto;
        }

        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }

        .modal-content {
          background: white;
          border-radius: 8px;
          width: 90%;
          max-width: 600px;
          max-height: 90vh;
          overflow-y: auto;
          box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
        }

        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 20px;
          border-bottom: 1px solid #e5e7eb;
        }

        .modal-header h3 {
          display: flex;
          align-items: center;
          margin: 0;
          font-size: 18px;
          color: #374151;
        }

        .modal-body {
          padding: 20px;
        }

        .modal-footer {
          padding: 20px;
          border-top: 1px solid #e5e7eb;
        }

        .close-button {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          border: none;
          border-radius: 4px;
          background: #f3f4f6;
          color: #6b7280;
          cursor: pointer;
          transition: all 0.2s;
        }

        .close-button:hover {
          background: #e5e7eb;
          color: #374151;
        }

        .modal-icon {
          margin-right: 8px;
        }

        .document-name {
          font-size: 14px;
          color: #666;
          font-weight: normal;
        }

        .scheduled-notifications-section {
          background: #f0f9ff;
          border: 2px solid #0ea5e9;
          border-radius: 8px;
          padding: 16px;
          margin-bottom: 20px;
        }

        .scheduled-title {
          display: flex;
          align-items: center;
          gap: 8px;
          color: #0c4a6e;
          margin-bottom: 12px;
          font-size: 16px;
          font-weight: 600;
        }

        .scheduled-notifications-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .scheduled-notification {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: white;
          border: 1px solid #bae6fd;
          border-radius: 6px;
          padding: 12px;
        }

        .notification-content {
          flex: 1;
        }

        .notification-description {
          display: flex;
          align-items: center;
          gap: 8px;
          font-weight: 500;
          color: #374151;
          margin-bottom: 6px;
        }

        .notification-details {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          font-size: 12px;
          color: #6b7280;
        }

        .notification-date,
        .notification-timing,
        .scheduled-time {
          background: #f3f4f6;
          padding: 2px 6px;
          border-radius: 4px;
        }

        .remove-notification-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          border: 1px solid #fca5a5;
          border-radius: 4px;
          background: #fef2f2;
          color: #dc2626;
          cursor: pointer;
          transition: all 0.2s;
        }

        .remove-notification-btn:hover {
          background: #fee2e2;
          border-color: #f87171;
        }

        .scheduling-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          color: white;
          z-index: 1001;
        }

        .scheduling-spinner {
          width: 40px;
          height: 40px;
          border: 3px solid rgba(255, 255, 255, 0.3);
          border-top: 3px solid white;
          border-radius: 50%;
          animation: spin 1s linear infinite;
          margin-bottom: 15px;
        }

        .message {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 12px;
          border-radius: 6px;
          margin-bottom: 15px;
          font-size: 14px;
        }

        .message.success {
          background: #d1fae5;
          color: #065f46;
          border: 1px solid #10b981;
        }

        .message.error {
          background: #fef2f2;
          color: #991b1b;
          border: 1px solid #ef4444;
        }

        .message.warning {
          background: #fffbeb;
          color: #92400e;
          border: 1px solid #f59e0b;
        }

        .loading-container {
          text-align: center;
          padding: 40px;
          color: #6b7280;
        }

        .loading-spinner {
          width: 40px;
          height: 40px;
          border: 3px solid #e5e7eb;
          border-top: 3px solid #3b82f6;
          border-radius: 50%;
          animation: spin 1s linear infinite;
          margin: 0 auto 15px;
        }

        @keyframes spin {
          0% {
            transform: rotate(0deg);
          }
          100% {
            transform: rotate(360deg);
          }
        }

        .days-input-section {
          background: #f8fafc;
          border: 2px solid #e2e8f0;
          border-radius: 8px;
          padding: 16px;
          margin-bottom: 20px;
          text-align: center;
        }

        .days-input-section p {
          color: #6b7280;
          margin-bottom: 16px;
          line-height: 1.5;
        }

        .days-input-container {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 12px;
        }

        .days-input {
          width: 60px;
          padding: 8px;
          border: 1px solid #d1d5db;
          border-radius: 4px;
          font-size: 14px;
          text-align: center;
        }

        .days-input:focus {
          outline: none;
          border-color: #3b82f6;
          box-shadow: 0 0 0 1px #3b82f6;
        }

        .days-label {
          color: #6b7280;
          font-size: 14px;
        }

        .reminders-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 15px;
        }

        .reminders-list h4 {
          color: #374151;
          font-size: 16px;
          margin: 0;
        }

        .header-info {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
        }

        .enabled-count {
          color: #6b7280;
          background: #f3f4f6;
          padding: 4px 8px;
          border-radius: 12px;
        }

        .notification-info {
          color: #059669;
          background: #d1fae5;
          padding: 4px 8px;
          border-radius: 12px;
        }

        .reminder-item {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 15px;
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 8px;
          margin-bottom: 10px;
          transition: all 0.2s;
        }

        .reminder-item:hover {
          border-color: #3b82f6;
          box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
        }

        .reminder-item.disabled {
          opacity: 0.6;
          background: #f9fafb;
        }

        .reminder-item.disabled:hover {
          border-color: #d1d5db;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }

        .reminder-bell-toggle {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 36px;
          height: 36px;
          border-radius: 50%;
          border: 2px solid;
          background: none;
          cursor: pointer;
          transition: all 0.2s;
        }

        .reminder-bell-toggle:hover:not(:disabled) {
          transform: scale(1.05);
        }

        .reminder-bell-toggle:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .bell-enabled {
          color: #ef4444;
        }

        .reminder-bell-toggle:has(.bell-enabled) {
          background: #fef2f2;
          border-color: #fecaca;
        }

        .reminder-bell-toggle:has(.bell-enabled):hover:not(:disabled) {
          background: #fee2e2;
          border-color: #fca5a5;
        }

        .bell-disabled {
          color: #9ca3af;
        }

        .reminder-bell-toggle:has(.bell-disabled) {
          background: #f9fafb;
          border-color: #e5e7eb;
        }

        .reminder-bell-toggle:has(.bell-disabled):hover:not(:disabled) {
          background: #f3f4f6;
          border-color: #d1d5db;
        }

        .reminder-content {
          flex: 1;
        }

        .reminder-description {
          font-weight: 500;
          color: #374151;
          margin-bottom: 6px;
          line-height: 1.4;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .reminder-status {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .notification-status {
          font-size: 12px;
          font-weight: 600;
          padding: 2px 6px;
          border-radius: 12px;
        }

        .notification-status.on {
          background: #d1fae5;
          color: #065f46;
        }

        .notification-status.off {
          background: #f3f4f6;
          color: #6b7280;
        }

        .scheduled-badge {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 10px;
          font-weight: 600;
          padding: 2px 6px;
          border-radius: 12px;
          background: #dbeafe;
          color: #1e40af;
        }

        .reminder-date {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 14px;
          color: #6b7280;
        }

        .empty-reminders {
          text-align: center;
          padding: 40px;
          color: #6b7280;
        }

        .empty-icon {
          width: 48px;
          height: 48px;
          color: #d1d5db;
          margin: 0 auto 15px;
        }

        .empty-reminders h4 {
          color: #374151;
          margin-bottom: 8px;
        }

        .modal-footer {
          display: flex;
          justify-content: flex-end;
          align-items: center;
          gap: 10px;
          padding-top: 20px;
          border-top: 1px solid #e5e7eb;
        }

        .footer-right {
          display: flex;
          gap: 10px;
        }

        .refresh-btn,
        .close-btn {
          padding: 10px 20px;
          border: none;
          border-radius: 6px;
          cursor: pointer;
          font-size: 14px;
          transition: all 0.2s;
        }

        .refresh-btn {
          background: #3b82f6;
          color: white;
        }

        .close-btn {
          background: #e5e7eb;
          color: #374151;
        }

        .refresh-btn:hover:not(:disabled) {
          background: #2563eb;
        }

        .close-btn:hover {
          background: #d1d5db;
        }

        .refresh-btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
};

export default SmartReminder;
