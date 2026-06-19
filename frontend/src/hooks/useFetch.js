import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../services/api";

/**
 * Generic async data hook with loading / error / refetch.
 * `fn` should be a stable function (wrap in useCallback at the call site
 * or pass a module-level helper) that returns a promise.
 */
export default function useFetch(fn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const run = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await fn();
      setData(result);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
  }, [run]);

  return { data, loading, error, refetch: run, setData };
}
