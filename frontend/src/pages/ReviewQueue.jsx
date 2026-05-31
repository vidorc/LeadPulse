import { useEffect, useState } from "react";
import api from "../services/api";

export default function ReviewQueue() {
  const [leads, setLeads] = useState([]);

  useEffect(() => {
    api.get("/leads/review-queue").then((res) => {
      setLeads(res.data);
    });
  }, []);

  const approveLead = async (id) => {
    await api.post(`/leads/override/${id}`, {
      decision: "hot_lead",
      review_notes: "Sales approved manually",
    });

    window.location.reload();
  };

  return (
    <div className="page">
      <h1>Manual Review Queue</h1>

      {leads.map((lead) => (
        <div className="card" key={lead.id}>
          <h3>{lead.name}</h3>
          <p>{lead.message}</p>

          <button onClick={() => approveLead(lead.id)}>
            Approve Hot Lead
          </button>
        </div>
      ))}
    </div>
  );
}