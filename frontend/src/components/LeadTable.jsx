import { useNavigate } from "react-router-dom";

export default function LeadTable({ leads }) {
  const navigate = useNavigate();

  return (
    <div className="card">
      <h2>All Leads</h2>

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Budget</th>
            <th>Decision</th>
            <th>Status</th>
          </tr>
        </thead>

        <tbody>
          {leads.map((lead) => (
            <tr
              key={lead.id}
              onClick={() => navigate(`/lead/${lead.id}`)}
              style={{ cursor: "pointer" }}
            >
              <td>{lead.name}</td>
              <td>{lead.budget}</td>
              <td>{lead.decision}</td>
              <td>{lead.requires_human_review}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}