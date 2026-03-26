-- 예시 4: 동적 SQL + 피벗 (PIVOT)
CREATE PROCEDURE GetProductPivotReport
    @StartYear INT,
    @EndYear   INT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @SQL NVARCHAR(MAX);
    DECLARE @Columns NVARCHAR(MAX);

    -- 월별 컬럼 목록 동적 생성
    SELECT @Columns = STRING_AGG(QUOTENAME(MonthName), ',')
    FROM (
        SELECT DISTINCT FORMAT(OrderDate, 'MMMM') MonthName
        FROM Orders
        WHERE YEAR(OrderDate) BETWEEN @StartYear AND @EndYear
    ) months;

    -- 피벗 쿼리
    SET @SQL = N'
    SELECT *
    FROM (
        SELECT p.ProductID, p.ProductName,
               FORMAT(o.OrderDate, ''MMMM'') AS Month,
               SUM(od.Quantity * od.UnitPrice) AS SalesAmount
        FROM Products p
        LEFT JOIN OrderDetails od ON p.ProductID = od.ProductID
        LEFT JOIN Orders o ON od.OrderID = o.OrderID
        WHERE YEAR(o.OrderDate) BETWEEN @StartYear AND @EndYear
    ) pivotdata
    PIVOT (
        SUM(SalesAmount)
        FOR Month IN (' + @Columns + ')
    ) AS pivottable
    ORDER BY ProductID';

    EXEC sp_executesql @SQL,
        N'@StartYear INT, @EndYear INT',
        @StartYear, @EndYear;
END
