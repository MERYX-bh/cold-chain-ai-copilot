-- ====================================================================
-- AGENT AUDIT LOG (written by the agent, read by the admin in the UI)
-- Run as the admin / sa user, after setup_security_and_view.sql
-- ====================================================================

IF OBJECT_ID('FDE_VIEWS.AgentAuditLog', 'U') IS NULL
BEGIN
    CREATE TABLE FDE_VIEWS.AgentAuditLog (
        LogID INT IDENTITY(1,1) PRIMARY KEY,
        Timestamp DATETIME DEFAULT GETDATE(),
        SessionID VARCHAR(50),
        NodeExecuted VARCHAR(50),
        ToolName VARCHAR(100),
        Content NVARCHAR(MAX)
    );
END
GO

-- The agent can only insert audit rows: it cannot read, edit or delete them.
GRANT INSERT ON FDE_VIEWS.AgentAuditLog TO USR_FDE_RO;
GO

-- Check (run as admin):
-- SELECT TOP 20 * FROM FDE_VIEWS.AgentAuditLog ORDER BY Timestamp DESC;
