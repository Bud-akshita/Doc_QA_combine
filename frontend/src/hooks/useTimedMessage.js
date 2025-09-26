import { useState, useEffect, useCallback, useRef } from "react";

export const useTimedMessage = (initialState = { text: "", type: "" }) => {
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
      }, 7000);
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