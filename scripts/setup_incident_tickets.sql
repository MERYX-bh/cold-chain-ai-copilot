-- ====================================================================
-- INCIDENT TICKETS (target of the create_incident_ticket action tool)
-- Run as the admin / sa user, after setup_security_and_view.sql
-- ====================================================================

CREATE TABLE FDE_VIEWS.IncidentTickets (
    TicketID INT IDENTITY(1,1) PRIMARY KEY,
    TicketRef VARCHAR(20) NOT NULL UNIQUE,
    CreatedAt DATETIME NOT NULL DEFAULT GETDATE(),
    SessionID VARCHAR(50) NULL,
    Title NVARCHAR(200) NOT NULL,
    Severity VARCHAR(10) NOT NULL CHECK (Severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    Description NVARCHAR(MAX) NOT NULL,
    RecommendedAction NVARCHAR(MAX) NOT NULL,
    Latitude FLOAT NULL,
    Longitude FLOAT NULL,
    Status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
);
GO

-- The agent can only insert tickets: it cannot read, edit or delete them.
GRANT INSERT ON FDE_VIEWS.IncidentTickets TO USR_FDE_RO;
GO

-- Check after a validated ticket (run as admin):
-- SELECT * FROM FDE_VIEWS.IncidentTickets ORDER BY CreatedAt DESC;
