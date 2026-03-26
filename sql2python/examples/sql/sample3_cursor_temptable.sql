-- 예시 3: 임시 테이블 + 커서 + 동적 처리
CREATE PROCEDURE GenerateSalesReport
    @StartDate DATE,
    @EndDate   DATE
AS
BEGIN
    SET NOCOUNT ON;

    -- 임시 테이블 (판매 요약)
    CREATE TABLE #SalesSummary (
        SalesPersonID INT,
        SalesPersonName NVARCHAR(200),
        TotalSales DECIMAL(18,2),
        OrderCount INT,
        AverageOrderValue DECIMAL(18,2)
    );

    -- 데이터 삽입
    INSERT INTO #SalesSummary
    SELECT sp.SalesPersonID, sp.Name,
           SUM(o.TotalAmount) TotalSales,
           COUNT(*) OrderCount,
           AVG(o.TotalAmount) AverageOrderValue
    FROM SalesPeople sp
    LEFT JOIN Orders o ON sp.SalesPersonID = o.SalesPersonID
           AND o.OrderDate BETWEEN @StartDate AND @EndDate
    GROUP BY sp.SalesPersonID, sp.Name;

    -- 커서: 상위 판매자 마킹
    DECLARE @SPId INT, @Sales DECIMAL(18,2);
    DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT SalesPersonID, TotalSales FROM #SalesSummary
        WHERE TotalSales > (SELECT AVG(TotalSales) FROM #SalesSummary)
        ORDER BY TotalSales DESC;

    OPEN cur;
    FETCH NEXT FROM cur INTO @SPId, @Sales;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        UPDATE SalesPeople
        SET IsTopPerformer = 1, LastReviewDate = GETDATE()
        WHERE SalesPersonID = @SPId;

        FETCH NEXT FROM cur INTO @SPId, @Sales;
    END
    CLOSE cur;
    DEALLOCATE cur;

    -- 최종 결과 반환
    SELECT * FROM #SalesSummary ORDER BY TotalSales DESC;

    DROP TABLE #SalesSummary;
END
