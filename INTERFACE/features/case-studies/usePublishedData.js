import { useEffect, useState } from 'react';

export default function usePublishedData(url) {
  const [state, setState] = useState({data:null,error:null});
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({data:null,error:null});
    fetch(url, {signal:controller.signal, cache:'no-cache'})
      .then(r => {if (!r.ok) throw new Error(`Evidence could not be loaded (${r.status}).`); return r.json();})
      .then(data => setState({data,error:null}))
      .catch(error => {if (error.name !== 'AbortError') setState({data:null,error:error.message});});
    return () => controller.abort();
  }, [url, attempt]);
  return {...state,retry:() => setAttempt(n => n+1)};
}
