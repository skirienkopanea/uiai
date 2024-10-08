
DROP TABLE IF EXISTS [Email];
DROP TABLE IF EXISTS [Appointment];
DROP TABLE IF EXISTS [Attachment];

CREATE TABLE [EMAIL]
(
    [EMAILID] INTEGER PRIMARY KEY AUTOINCREMENT,
    [DATE] DATETIME,
    [FROM_NAME] NVARCHAR(50),
    [FROM_ADDRESS] NVARCHAR(255),
    [TO_NAME] NVARCHAR(255),
    [TO_ADDRESS] NVARCHAR(255),
    [CC_NAME] NVARCHAR(255),
    [CC_ADDRESS] NVARCHAR(255),
    [SUBJECT] NVARCHAR(160),
    [BODY] TEXT,
    FOREIGN KEY ([EMAILID]) REFERENCES [ATTACHMENT] ([EMAILID]) 
		ON DELETE NO ACTION ON UPDATE NO ACTION
        
);

CREATE TABLE [ATTACHMENT]
(
    [EMAILID] INTEGER  NOT NULL,
    [NAME] NVARCHAR(255),
    [PATH] NVARCHAR(255),
    [FILE_EXTENSION] NVARCHAR(10),
    CONSTRAINT check_file_extension CHECK (FILE_EXTENSION GLOB '[a-zA-Z]*')
);

CREATE TABLE [APPOINTMENT]
(
    [NAME] NVARCHAR(100),
    [START_DATE] DATETIME  NOT NULL,
    [END_DATE] DATETIME  NOT NULL
);

CREATE INDEX [IFK_EMAIL_ATTACHMENT_ID] ON [EMAIL] ([EMAILID]);