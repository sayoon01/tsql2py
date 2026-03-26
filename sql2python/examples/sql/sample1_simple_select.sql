-- 예시 1: 단순 조회 + 조건 분기
CREATE PROCEDURE GetEmployeesByDepartment
    @DeptID     INT,
    @ActiveOnly BIT = 1,
    @SortOrder  NVARCHAR(10) = 'ASC'
AS
BEGIN
    SET NOCOUNT ON;

    IF @SortOrder NOT IN ('ASC', 'DESC')
        SET @SortOrder = 'ASC';

    IF @ActiveOnly = 1
    BEGIN
        SELECT EmployeeID, FirstName, LastName, Email, HireDate, Salary
        FROM Employees
        WHERE DepartmentID = @DeptID AND IsActive = 1
        ORDER BY LastName;
    END
    ELSE
    BEGIN
        SELECT EmployeeID, FirstName, LastName, Email, HireDate, Salary
        FROM Employees
        WHERE DepartmentID = @DeptID
        ORDER BY LastName;
    END
END
