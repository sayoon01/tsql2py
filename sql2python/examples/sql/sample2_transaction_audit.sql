-- 예시 2: 트랜잭션 + 감사 로그 + OUTPUT
CREATE PROCEDURE TransferFunds
    @FromAccountID  INT,
    @ToAccountID    INT,
    @Amount         DECIMAL(18,2),
    @TransferID     INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 잔액 확인
        DECLARE @Balance DECIMAL(18,2);
        SELECT @Balance = Balance FROM Accounts WHERE AccountID = @FromAccountID;

        IF @Balance IS NULL
            RAISERROR('출금 계좌가 존재하지 않습니다.', 16, 1);
        IF @Balance < @Amount
            RAISERROR('잔액이 부족합니다.', 16, 1);

        -- 출금
        UPDATE Accounts
        SET Balance = Balance - @Amount, ModifiedDate = GETDATE()
        WHERE AccountID = @FromAccountID;

        -- 입금
        UPDATE Accounts
        SET Balance = Balance + @Amount, ModifiedDate = GETDATE()
        WHERE AccountID = @ToAccountID;

        -- 이체 기록
        INSERT INTO Transfers (FromAccountID, ToAccountID, Amount, TransferDate, Status)
        VALUES (@FromAccountID, @ToAccountID, @Amount, GETDATE(), 'COMPLETED');

        SET @TransferID = SCOPE_IDENTITY();

        -- 감사 로그
        INSERT INTO AuditLog (Action, TableName, RecordID, Details, CreatedDate)
        VALUES ('TRANSFER', 'Accounts', @TransferID,
                'From: ' + CAST(@FromAccountID AS VARCHAR) + ' To: ' + CAST(@ToAccountID AS VARCHAR) + ' Amount: ' + CAST(@Amount AS VARCHAR),
                GETDATE());

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        INSERT INTO AuditLog (Action, TableName, RecordID, Details, CreatedDate)
        VALUES ('TRANSFER_FAILED', 'Accounts', 0, ERROR_MESSAGE(), GETDATE());

        THROW;
    END CATCH
END
