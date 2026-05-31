import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";
import LeadTable from "../components/LeadTable";

export default function Dashboard() {
  const [metrics, setMetrics] = useState({
    total_leads: 0,
    hot_leads: 0,
    manual_reviews: 0,
  });

  const [leads, setLeads] = useState([]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const metricsRes = await api.get("/leads/dashboard/summary");
        const leadsRes = await api.get("/leads/");

        console.log("metrics:", metricsRes.data);
        console.log("leads:", leadsRes.data);

        setMetrics(metricsRes.data);
        setLeads(leadsRes.data);
      } catch (err) {
        console.error(err);
      }
    };

    fetchData();
  }, []);

  return (
    <div className="page">
      <div className="topbar">
        <h1>LeadPulse Dashboard</h1>

        <Link to="/review">
          <button>Review Queue</button>
        </Link>
      </div>

      <div className="metrics">
        <div className="metric-card">
          <h3>Total Leads</h3>
          <p>{metrics.total_leads}</p>
        </div>

        <div className="metric-card">
          <h3>Hot Leads</h3>
          <p>{metrics.hot_leads}</p>
        </div>

        <div className="metric-card">
          <h3>Manual Reviews</h3>
          <p>{metrics.manual_reviews}</p>
        </div>
      </div>

      <LeadTable leads={leads} />
    </div>
  );
}